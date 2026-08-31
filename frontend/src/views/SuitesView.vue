<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelsStore } from "@/stores/models";
import DatasetPicker from "@/components/common/DatasetPicker.vue";
import PageHero from "@/components/layouts/PageHero.vue";
import Stepper from "@/components/layouts/Stepper.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import {
  cancelSuite,
  fetchDatasets,
  fetchStressDatasets,
  finalStatus,
  formatDate,
  getSuite,
  listSuites,
  parseIntegerList,
  runSuite,
  toNumber,
  type DatasetMeta,
  type StressDatasetMeta,
} from "@/api/evaluations";

const store = useModelsStore();
const loading = ref(false);
const submitting = ref(false);
const tasks = ref<Record<string, any>[]>([]);
const selected = ref<Record<string, any> | null>(null);

// Intelligence datasets
const datasetsLoading = ref(false);
const datasetMap = ref<Record<string, DatasetMeta>>({});
const defaultDatasets = ref<string[]>([]);
const chosenDatasets = ref<string[]>([]);
const chosenSubsets = ref<Record<string, string[]>>({});
const subsetOverride = ref<Record<string, boolean>>({});

// Stress datasets
const stressDatasetsLoading = ref(false);
const stressDatasets = ref<Record<string, StressDatasetMeta>>({});
const defaultStressDataset = ref("");
const selectedStressDataset = ref("");

const currentStep = ref(0);

const wizardSteps = [
  { key: "lane",    title: "选择评测线", description: "勾选要跑的基础 / 压测 / 能力" },
  { key: "dataset", title: "能力数据集", description: "选择本地可用的 EvalScope 数据集", optional: true },
  { key: "params",  title: "参数",       description: "设置压测并发 / 样本上限" },
  { key: "judge",   title: "临时模型",   description: "快速模式: 临时配置一个模型", optional: true },
  { key: "confirm", title: "确认启动",   description: "检查并启动套件" },
];

const form = ref({
  runGateway: true,
  runIntelligence: true,
  runStress: true,
  intelligenceLimit: "",
  intelligenceEvalBatchSize: "",
  stressParallel: "1,5,10,20",
  stressNumber: "10,50,100,200",
  stressStream: "",
  stressMinTokens: "",
  stressMaxTokens: "",
  stressDatasetPath: "",
  quickMode: false,
  quickUrl: "",
  quickKey: "",
  quickModel: "",
  quickName: "",
});

const localDatasetEntries = computed(() =>
  Object.entries(datasetMap.value)
    .filter(([, meta]) => meta.available_local)
    .sort(([a], [b]) => {
      const da = defaultDatasets.value.includes(a);
      const db = defaultDatasets.value.includes(b);
      if (da !== db) return da ? -1 : 1;
      return a.localeCompare(b);
    }),
);

const stressDatasetList = computed(() =>
  Object.values(stressDatasets.value).sort((a, b) => Number(b.is_default) - Number(a.is_default)),
);

function statusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "running" || status === "pending" || status === "queued") return "warning";
  return "info";
}

function stepStatusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "running") return "warning";
  return "info";
}



function pickStressDataset(name: string) {
  selectedStressDataset.value = name;
  form.value.stressDatasetPath = "";
}

async function loadDatasets() {
  datasetsLoading.value = true;
  try {
    const result = await fetchDatasets();
    datasetMap.value = result.datasets;
    defaultDatasets.value = result.default_datasets;
    chosenDatasets.value = localDatasetEntries.value
      .filter(([name]) => defaultDatasets.value.includes(name))
      .map(([name]) => name);
    if (!chosenDatasets.value.length) chosenDatasets.value = localDatasetEntries.value.map(([name]) => name);
  } finally {
    datasetsLoading.value = false;
  }
}

async function loadStressDatasets() {
  stressDatasetsLoading.value = true;
  try {
    const result = await fetchStressDatasets();
    stressDatasets.value = result.datasets;
    defaultStressDataset.value = result.default_dataset;
    if (!selectedStressDataset.value && result.default_dataset) {
      selectedStressDataset.value = result.default_dataset;
    }
  } finally {
    stressDatasetsLoading.value = false;
  }
}

async function reload() {
  loading.value = true;
  try {
    tasks.value = await listSuites();
    if (selected.value) selected.value = await getSuite(selected.value.suite_id);
  } finally {
    loading.value = false;
  }
}

async function selectTask(row: Record<string, any>) {
  selected.value = await getSuite(row.suite_id);
}

function buildPayload() {
  if (!form.value.runGateway && !form.value.runIntelligence && !form.value.runStress) {
    throw new Error("至少选择一条评测线");
  }
  const payload: Record<string, unknown> = {
    run_gateway: form.value.runGateway,
    run_intelligence: form.value.runIntelligence,
    run_stress: form.value.runStress,
  };

  if (form.value.quickMode) {
    if (!form.value.quickUrl?.trim()) throw new Error("请填写模型 API URL");
    if (!form.value.quickModel?.trim()) throw new Error("请填写模型名称");
    payload.url = form.value.quickUrl.trim();
    payload.key = form.value.quickKey?.trim() || "";
    payload.model = form.value.quickModel.trim();
    if (form.value.quickName?.trim()) payload.name = form.value.quickName.trim();
  } else {
    if (!store.currentId) throw new Error("请先选择当前模型");
    payload.model_id = store.currentId;
  }

  if (form.value.runIntelligence) {
    const localNames = localDatasetEntries.value.map(([name]) => name);
    const finalDatasets = chosenDatasets.value.length ? chosenDatasets.value : localNames;
    if (!finalDatasets.length) throw new Error("未发现本地可用数据集");
    payload.intelligence_datasets = finalDatasets;
    const limit = toNumber(form.value.intelligenceLimit);
    if (limit !== undefined) payload.intelligence_limit = limit;
    const batchSize = toNumber(form.value.intelligenceEvalBatchSize);
    if (batchSize !== undefined) payload.intelligence_eval_batch_size = batchSize;

    // Build dataset_args for subset overrides
    const datasetArgs: Record<string, Record<string, unknown>> = {};
    for (const name of finalDatasets) {
      if (subsetOverride.value[name] && chosenSubsets.value[name]?.length) {
        datasetArgs[name] = { subset_list: chosenSubsets.value[name] };
      }
    }
    if (Object.keys(datasetArgs).length) payload.intelligence_dataset_args = datasetArgs;
  }

  if (form.value.runStress) {
    const parallel = parseIntegerList(form.value.stressParallel);
    const number = parseIntegerList(form.value.stressNumber);
    if (parallel && number && parallel.length !== number.length) {
      throw new Error("parallel 与 number 必须一一对应");
    }
    const stressOptions: Record<string, unknown> = {};
    if (parallel) stressOptions.parallel = parallel;
    if (number) stressOptions.number = number;
    if (form.value.stressStream) stressOptions.stream = form.value.stressStream === "true";
    if (selectedStressDataset.value) stressOptions.dataset = selectedStressDataset.value;
    if (form.value.stressDatasetPath) stressOptions.dataset_path = form.value.stressDatasetPath;
    const minTokens = toNumber(form.value.stressMinTokens);
    const maxTokens = toNumber(form.value.stressMaxTokens);
    if (minTokens !== undefined) stressOptions.min_tokens = minTokens;
    if (maxTokens !== undefined) stressOptions.max_tokens = maxTokens;
    if (Object.keys(stressOptions).length) payload.stress_options = stressOptions;
  }

  return payload;
}

async function submit() {
  submitting.value = true;
  try {
    const payload = buildPayload();
    const task = await runSuite(payload, form.value.quickMode);
    ElMessage.success(`已启动一键评测：${task.suite_id}`);
    await reload();
    await selectTask(task);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

async function cancelTask(suiteId: string) {
  try {
    await ElMessageBox.confirm("确定取消该评测任务？", "取消确认", { type: "warning" });
    await cancelSuite(suiteId);
    ElMessage.success("已取消");
    await reload();
  } catch (err) {
    if (err !== "cancel") ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}

const steps = computed(() => (selected.value?.steps as any[]) || []);

onMounted(() => {
  loadDatasets();
  loadStressDatasets();
  reload();
});
</script>

<template>
<PageHero
    eyebrow="ONE-CLICK SUITE"
    title="一键完整评测"
    description="串联基础 / 压测 / 能力三条评测线, 一次启动, 生成统一总览报告。适合上线前 / 模型升级后做完整基线。"
  >
    <template #actions>
      <el-button size="small" :disabled="currentStep === 0" @click="currentStep--">上一步</el-button>
      <el-button size="small" type="primary" :disabled="currentStep === wizardSteps.length - 1" @click="currentStep++">下一步</el-button>
    </template>
  </PageHero>

  <Stepper :steps="wizardSteps" :current="currentStep" clickable @jump="(i) => currentStep = i" />

    <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <p class="muted">串起基础 / 压测 / 能力三条评测线，生成统一总览报告。可按需勾选评测线。</p>
      <el-form label-position="top">
        <!-- Step 0: 选择评测线 + 模型 -->
        <div v-show="currentStep === 0">
          <el-form-item label="评测线选择">
            <el-checkbox v-model="form.runGateway">基础评测</el-checkbox>
            <el-checkbox v-model="form.runStress">压测评测</el-checkbox>
            <el-checkbox v-model="form.runIntelligence">能力评测</el-checkbox>
          </el-form-item>
          <el-form-item>
            <el-switch v-model="form.quickMode" active-text="快速模式（临时模型）" inactive-text="使用已注册模型" />
          </el-form-item>
          <el-form-item v-if="!form.quickMode" label="当前模型">
            <el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled />
          </el-form-item>
          <el-alert v-if="!form.runGateway && !form.runStress && !form.runIntelligence" type="warning" :closable="false" show-icon>
            请至少勾选一条评测线
          </el-alert>
        </div>

        <!-- Step 1: 能力数据集 -->
        <div v-show="currentStep === 1">
          <template v-if="form.runIntelligence">
            <div class="section-title">能力评测数据集</div>
            <DatasetPicker
              v-model="chosenDatasets"
              :datasets="datasetMap"
              :default-datasets="defaultDatasets"
              :subset-model-value="chosenSubsets"
              :subset-override="subsetOverride"
              @update:subset-model-value="(v) => (chosenSubsets = v)"
              @update:subset-override="(v) => (subsetOverride = v)"
            />
            <el-row :gutter="12">
              <el-col :span="12"><el-form-item label="limit"><el-input v-model="form.intelligenceLimit" placeholder="留空=不限" /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="eval_batch_size"><el-input v-model="form.intelligenceEvalBatchSize" placeholder="默认" /></el-form-item></el-col>
            </el-row>
          </template>
          <EmptyState v-else title="未启用能力评测" description="回到第 1 步勾选能力评测" variant="list" />
        </div>

        <!-- Step 2: 压测参数 -->
        <div v-show="currentStep === 2">
          <template v-if="form.runStress">
            <div class="section-title">压测数据集</div>
            <div class="dataset-cards" v-loading="stressDatasetsLoading">
              <div
                v-for="ds in stressDatasetList"
                :key="ds.name"
                class="dataset-card"
                :class="{ 'dataset-card--active': selectedStressDataset === ds.name }"
                @click="pickStressDataset(ds.name)"
              >
                <div class="dataset-card__header">
                  <span class="dataset-card__name">{{ ds.pretty_name || ds.name }}</span>
                  <el-tag v-if="ds.is_default" size="small" type="success">默认</el-tag>
                  <el-tag v-if="ds.available_local" size="small" type="info">本地</el-tag>
                </div>
                <p class="dataset-card__desc muted">{{ ds.description || '暂无描述' }}</p>
              </div>
            </div>
            <el-form-item label="dataset_path（可选）"><el-input v-model="form.stressDatasetPath" placeholder="留空自动解析" /></el-form-item>
            <el-row :gutter="12">
              <el-col :span="12"><el-form-item label="parallel"><el-input v-model="form.stressParallel" /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="number"><el-input v-model="form.stressNumber" /></el-form-item></el-col>
            </el-row>
            <el-form-item label="stream">
              <el-select v-model="form.stressStream" class="full-width">
                <el-option label="默认" value="" />
                <el-option label="true" value="true" />
                <el-option label="false" value="false" />
              </el-select>
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12"><el-form-item label="最小 token"><el-input v-model="form.stressMinTokens" /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="最大 token"><el-input v-model="form.stressMaxTokens" /></el-form-item></el-col>
            </el-row>
          </template>
          <EmptyState v-else title="未启用压测评测" description="回到第 1 步勾选压测评测" variant="list" />
        </div>

        <!-- Step 3: 临时模型 -->
        <div v-show="currentStep === 3">
          <template v-if="form.quickMode">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>快速模式: 配置一个临时模型跑此套件</template>
            </el-alert>
            <el-form-item label="API URL"><el-input v-model="form.quickUrl" placeholder="https://..." /></el-form-item>
            <el-form-item label="API Key"><el-input v-model="form.quickKey" placeholder="可选" show-password /></el-form-item>
            <el-form-item label="模型名称"><el-input v-model="form.quickModel" placeholder="gpt-4o-mini" /></el-form-item>
            <el-form-item label="显示名称（可选）"><el-input v-model="form.quickName" /></el-form-item>
          </template>
          <EmptyState v-else title="已选择注册模型" description="如需临时模型, 回到第 1 步开启快速模式" variant="success" />
        </div>

        <!-- Step 4: 确认 + 启动 -->
        <div v-show="currentStep === 4" class="lb-suite-confirm">
          <h3>请确认配置</h3>
          <ul class="lb-suite-confirm__list">
            <li><span>基础评测</span><b>{{ form.runGateway ? '启用' : '跳过' }}</b></li>
            <li><span>压测评测</span><b>{{ form.runStress ? '启用 · 数据集 ' + (selectedStressDataset || '默认') : '跳过' }}</b></li>
            <li><span>能力评测</span><b>{{ form.runIntelligence ? '启用 · ' + chosenDatasets.length + ' 个数据集' : '跳过' }}</b></li>
            <li><span>模型</span><b>{{ form.quickMode ? (form.quickModel || '未填') : (store.currentModel?.name || store.currentId || '未选') }}</b></li>
            <li><span>压测并发</span><b>{{ form.stressParallel }}</b></li>
            <li><span>压测请求数</span><b>{{ form.stressNumber }}</b></li>
          </ul>
          <el-button type="primary" size="large" :loading="submitting" @click="submit">启动一键评测</el-button>
        </div>
      </el-form>

      <div v-if="currentStep < 4" class="lb-suite-wizard-foot">
        <el-button @click="currentStep = 4" :disabled="!form.runGateway && !form.runStress && !form.runIntelligence">跳到确认 →</el-button>
      </div>
    </el-card>

    <el-card class="panel-card" shadow="never">
      <div class="lb-suite-list-head">
        <el-button size="small" @click="reload">刷新</el-button>
      </div>
      <EmptyState
        v-if="!loading && tasks.length === 0"
        title="还没有 Suite"
        description="启动一键评测后会在这里显示, 通常包含基础/压测/能力三条线结果。"
        variant="list"
        action-label="去配置"
        @action="currentStep = 0"
      />
      <el-table
        v-else
        v-loading="loading"
        :data="tasks"
        height="520"
        highlight-current-row
        @row-click="selectTask"
      >
        <el-table-column prop="suite_id" label="Suite" min-width="210" show-overflow-tooltip />
        <el-table-column prop="model_id" label="模型" width="130" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="更新" width="170"><template #default="{ row }">{{ formatDate(row.updated_at) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card detail-card" shadow="never">
      <EmptyState
        v-if="!selected"
        title="还没有选择 Suite"
        description="从左侧列表选一个 Suite 查看详细步骤, 耗时, 总览报告链接。"
        variant="list"
      />
      <template v-else>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Suite ID">{{ selected.suite_id }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ selected.model_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(selected.status)">{{ selected.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="当前步骤">{{ selected.current_step || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(selected.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">评测步骤</div>
        <el-timeline>
          <el-timeline-item
            v-for="step in steps"
            :key="step.name"
            :type="stepStatusType(step.status)"
            :timestamp="formatDate(step.completed_at || step.started_at)"
          >
            <div class="step-head">
              <span class="step-title">{{ step.title }}</span>
              <el-tag size="small" :type="stepStatusType(step.status)">{{ step.status }}</el-tag>
            </div>
            <p v-if="step.message" class="muted step-msg">{{ step.message }}</p>
            <el-link v-if="step.task_id && step.name === 'gateway'" type="primary" :href="`/api/reports/${step.task_id}`" target="_blank">查看网关报告</el-link>
            <el-link v-if="step.task_id && step.name === 'intelligence'" type="primary" :href="`/api/intelligence/tasks/${step.task_id}/result`" target="_blank">查看能力评测结果</el-link>
            <el-link v-if="step.task_id && step.name === 'stress'" type="primary" :href="`/api/stress/reports/${step.task_id}`" target="_blank">查看压测报告</el-link>
          </el-timeline-item>
        </el-timeline>

        <div class="detail-actions">
          <el-button v-if="!finalStatus(selected.status)" type="danger" plain @click="cancelTask(selected.suite_id)">取消任务</el-button>
          <el-link v-if="selected.overview_report_path" type="primary" :href="`/api/suites/${selected.suite_id}/report`" target="_blank">打开总览报告</el-link>
        </div>

        <el-alert v-if="selected.errors?.length" class="mt" type="error" :closable="false" :title="`错误 ${selected.errors.length} 条`" />
        <div v-if="selected.errors?.length" class="error-list">
          <div v-for="(err, i) in selected.errors" :key="i" class="error-item">
            <el-tag size="small" type="danger">{{ err.step }}</el-tag>
            <span>{{ err.message }}</span>
          </div>
        </div>
      </template>
    </el-card>
  </section>
</template>

<style scoped>
.lb-suite-list-head {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
</style>
