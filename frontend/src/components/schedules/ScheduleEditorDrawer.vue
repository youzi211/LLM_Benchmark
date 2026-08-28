<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useModelsStore } from "@/stores/models";
import {
  createSchedule,
  fetchDatasets,
  fetchStressDatasets,
  fetchSandboxHealth,
  parseIntegerList,
  toNumber,
  type DatasetMeta,
  type StressDatasetMeta,
  fetchSuiteProfiles,
  type SuiteProfile,
  type EvalScopeHealthStatus,
} from "@/api/evaluations";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
  (event: "created"): void;
}>();

const store = useModelsStore();
const submitting = ref(false);
const loading = ref(false);
const sandboxTesting = ref(false);
const sandboxHealth = ref<EvalScopeHealthStatus | null>(null);
const activeTab = ref("basic");
const loaded = ref(false);

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

const profiles = ref<SuiteProfile[]>([]);
const profilesLoading = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

function defaultForm() {
  return {
    name: "",
    model_id: "" as string,
    profile: "scheduled_light",
    runGateway: true,
    runIntelligence: true,
    runStress: true,
    timeOfDay: "02:00",
    intervalDays: 1,
    runOnce: false,
    runDate: "" as string,
    intelligenceLimit: "",
    intelligenceEvalBatchSize: "",
    stressParallel: "1,5,10",
    stressNumber: "10,50,100",
    stressStream: "",
    stressMinTokens: "",
    stressMaxTokens: "",
    stressDatasetPath: "",
  };
}

const form = ref(defaultForm());

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
  Object.values(stressDatasets.value)
    .filter((item) => item.available_local)
    .sort((a, b) => Number(b.is_default) - Number(a.is_default)),
);

const selectedProfile = computed(() => profiles.value.find((item) => item.profile_id === form.value.profile));

const chosenDatasetMetas = computed(() =>
  chosenDatasets.value.map((name) => ({ name, meta: datasetMap.value[name] })).filter((item) => item.meta),
);

async function loadProfiles() {
  profilesLoading.value = true;
  try {
    profiles.value = await fetchSuiteProfiles();
  } finally {
    profilesLoading.value = false;
  }
}

function profileDatasetLabels(profile?: SuiteProfile) {
  return (profile?.intelligence_datasets || []).map((name) => datasetMap.value[name]?.pretty_name || name);
}

function profileDatasetDetail(name: string) {
  const meta = datasetMap.value[name];
  if (!meta) return name;
  const subsetCount = meta.configured_subset_list?.length || meta.subset_count || meta.subsets?.length || 0;
  const suffix = subsetCount ? ` · ${subsetCount} 个子集` : "";
  return `${meta.pretty_name || name}${suffix}`;
}

function firstLocalStressDataset() {
  return stressDatasets.value[defaultStressDataset.value]?.available_local
    ? defaultStressDataset.value
    : stressDatasetList.value[0]?.name || "";
}

function profileStressDatasetName(profile?: SuiteProfile) {
  const raw = profile?.stress_options?.dataset;
  if (typeof raw !== "string" || !raw) return firstLocalStressDataset() || "默认";
  return stressDatasets.value[raw]?.pretty_name || raw;
}

function profileListValue(value: unknown, fallback = "默认") {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function profileLaneLabels(profile?: SuiteProfile) {
  if (!profile) return [];
  const lanes: string[] = [];
  if (profile.run_gateway !== false) lanes.push("基础");
  if (profile.run_stress !== false) lanes.push("压测");
  if (profile.run_intelligence !== false) lanes.push("能力");
  return lanes;
}

function healthTagType(status?: string) {
  if (status === "ok") return "success";
  if (status === "disabled" || status === "unknown" || status === "missing") return "warning";
  if (status === "error") return "danger";
  return "info";
}

function healthMessage(health: EvalScopeHealthStatus | null) {
  if (!health) return "尚未测试";
  if (health.status === "ok") return health.checked_url ? `主服务正常，远端 Sandbox 可用：${health.checked_url}` : "主服务正常，Sandbox 可用";
  if (health.status === "disabled") return "主服务正常，但 Sandbox 配置未启用";
  const detail = typeof health.error === "string" ? health.error : health.message || health.status;
  return `主服务正常，远端 Sandbox 探测未通过：${detail}`;
}

async function testSandbox() {
  sandboxTesting.value = true;
  sandboxHealth.value = null;
  try {
    sandboxHealth.value = await fetchSandboxHealth(true);
    if (sandboxHealth.value.status === "ok") ElMessage.success("Sandbox 可用");
    else ElMessage.warning(`Sandbox 状态：${sandboxHealth.value.status}`);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    sandboxTesting.value = false;
  }
}

function locallyAvailableProfileDatasets(profile?: SuiteProfile) {
  const names = profile?.intelligence_datasets || [];
  if (!names.length) return [];
  return names.filter((name) => datasetMap.value[name]?.available_local !== false);
}

function applyProfileDefaults(profileId = form.value.profile) {
  const profile = profiles.value.find((item) => item.profile_id === profileId);
  if (!profile) return;

  if (profile.run_gateway !== undefined && profile.run_gateway !== null) form.value.runGateway = profile.run_gateway;
  if (profile.run_intelligence !== undefined && profile.run_intelligence !== null) form.value.runIntelligence = profile.run_intelligence;
  if (profile.run_stress !== undefined && profile.run_stress !== null) form.value.runStress = profile.run_stress;

  const profileDatasets = locallyAvailableProfileDatasets(profile);
  if (profile.intelligence_datasets?.length) {
    chosenDatasets.value = profileDatasets;
  }
  chosenSubsets.value = {};
  subsetOverride.value = {};

  form.value.intelligenceLimit = profile.intelligence_limit === null || profile.intelligence_limit === undefined ? "" : String(profile.intelligence_limit);
  form.value.intelligenceEvalBatchSize = profile.intelligence_eval_batch_size === null || profile.intelligence_eval_batch_size === undefined ? "" : String(profile.intelligence_eval_batch_size);

  const stress = profile.stress_options || {};
  const stressDataset = typeof stress.dataset === "string" ? stress.dataset : "";
  selectedStressDataset.value = stressDataset && stressDatasets.value[stressDataset]?.available_local
    ? stressDataset
    : firstLocalStressDataset() || selectedStressDataset.value;
  form.value.stressDatasetPath = "";
  form.value.stressParallel = Array.isArray(stress.parallel) ? stress.parallel.join(",") : "";
  form.value.stressNumber = Array.isArray(stress.number) ? stress.number.join(",") : "";
  form.value.stressStream = typeof stress.stream === "boolean" ? String(stress.stream) : "";
  form.value.stressMinTokens = stress.min_tokens === null || stress.min_tokens === undefined ? "" : String(stress.min_tokens);
  form.value.stressMaxTokens = stress.max_tokens === null || stress.max_tokens === undefined ? "" : String(stress.max_tokens);
}

function hasSubsets(meta: DatasetMeta) {
  return (meta.subsets?.length || 0) > 0;
}

function subsetTitle(meta: DatasetMeta) {
  const total = meta.subsets?.length || 0;
  const configured = meta.configured_subset_list?.length || 0;
  if (!total && !configured) return "子集信息";
  if (configured) return `子集：本地 ${total} 个 · 默认运行 ${configured} 个`;
  return `子集：本地 ${total} 个`;
}

function toggleSubsetOverride(name: string) {
  subsetOverride.value[name] = !subsetOverride.value[name];
  if (subsetOverride.value[name]) {
    const meta = datasetMap.value[name];
    chosenSubsets.value[name] = meta?.configured_subset_list?.length
      ? [...meta.configured_subset_list]
      : [...(meta?.subsets || [])];
  } else {
    delete chosenSubsets.value[name];
  }
}

watch(chosenDatasets, (current) => {
  const selected = new Set(current);
  for (const name of Object.keys(subsetOverride.value)) {
    if (!selected.has(name)) delete subsetOverride.value[name];
  }
  for (const name of Object.keys(chosenSubsets.value)) {
    if (!selected.has(name)) delete chosenSubsets.value[name];
  }
});

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
    if (!selectedStressDataset.value) {
      selectedStressDataset.value = firstLocalStressDataset();
    }
  } finally {
    stressDatasetsLoading.value = false;
  }
}

async function ensureLoaded() {
  if (loaded.value) return;
  loading.value = true;
  try {
    await Promise.all([store.load(), loadProfiles(), loadDatasets(), loadStressDatasets()]);
    applyProfileDefaults();
    loaded.value = true;
  } finally {
    loading.value = false;
  }
}

function buildPayload() {
  if (!form.value.name?.trim()) throw new Error("请填写任务名称");
  const modelId = form.value.model_id || store.currentId;
  if (!modelId) throw new Error("请选择模型");
  if (!form.value.runGateway && !form.value.runIntelligence && !form.value.runStress) {
    throw new Error("至少选择一条评测线");
  }
  const payload: Record<string, unknown> = {
    name: form.value.name.trim(),
    model_id: modelId,
    profile: form.value.profile,
    run_gateway: form.value.runGateway,
    run_intelligence: form.value.runIntelligence,
    run_stress: form.value.runStress,
    time_of_day: form.value.timeOfDay,
    interval_days: form.value.intervalDays,
    run_once: form.value.runOnce,
  };

  if (form.value.runOnce && form.value.runDate) {
    payload.run_date = form.value.runDate;
  }

  if (form.value.runIntelligence) {
    const localNames = new Set(localDatasetEntries.value.map(([name]) => name));
    const finalDatasets = chosenDatasets.value.filter((name) => localNames.has(name));
    if (!finalDatasets.length) throw new Error("请至少选择一个本地可用的能力评测数据集");
    payload.intelligence_datasets = finalDatasets;
    const limit = toNumber(form.value.intelligenceLimit);
    if (limit !== undefined) payload.intelligence_limit = limit;
    const batchSize = toNumber(form.value.intelligenceEvalBatchSize);
    if (batchSize !== undefined) payload.intelligence_eval_batch_size = batchSize;

    const datasetArgs: Record<string, Record<string, unknown>> = {};
    for (const name of finalDatasets) {
      if (subsetOverride.value[name] && chosenSubsets.value[name]?.length) {
        datasetArgs[name] = { subset_list: chosenSubsets.value[name] };
      }
    }
    if (Object.keys(datasetArgs).length) payload.intelligence_dataset_args = datasetArgs;
  }

  if (form.value.runStress) {
    if (!selectedStressDataset.value || !stressDatasets.value[selectedStressDataset.value]?.available_local) {
      throw new Error("请先选择一个本地可用的压测数据集");
    }
    const parallel = parseIntegerList(form.value.stressParallel);
    const number = parseIntegerList(form.value.stressNumber);
    if (parallel) payload.stress_parallel = parallel;
    if (number) payload.stress_number = number;
    const stressOptions: Record<string, unknown> = {};
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

function resetForm() {
  form.value = defaultForm();
  activeTab.value = "basic";
  chosenSubsets.value = {};
  subsetOverride.value = {};
  selectedStressDataset.value = firstLocalStressDataset();
  if (loaded.value) applyProfileDefaults();
}

function closeDrawer() {
  visible.value = false;
}

async function submit() {
  submitting.value = true;
  try {
    const payload = buildPayload();
    await createSchedule(payload);
    ElMessage.success("定时任务已创建");
    emit("created");
    closeDrawer();
    resetForm();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void ensureLoaded();
  },
);

onMounted(() => {
  void ensureLoaded();
});
</script>

<template>
  <el-drawer v-model="visible" title="创建定时任务" size="760px" class="schedule-editor-drawer" destroy-on-close>
    <div v-loading="loading" class="schedule-editor">
      <el-alert
        class="schedule-editor__hint"
        type="info"
        :closable="false"
        title="先选 Profile 使用系统默认配置，再按需展开能力/压测页签做精细调整。"
      />

      <el-tabs v-model="activeTab" class="schedule-editor-tabs">
        <el-tab-pane label="基础设置" name="basic">
          <el-form label-position="top">
            <el-form-item label="任务名称">
              <el-input v-model="form.name" placeholder="如：每日能力评测" />
            </el-form-item>
            <el-form-item label="模型">
              <el-select v-model="form.model_id" placeholder="选择模型" class="full-width" :loading="store.loading">
                <el-option v-for="m in store.models" :key="m.id" :label="m.name ?? m.model ?? m.id" :value="m.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="Profile">
              <el-select
                v-model="form.profile"
                class="full-width"
                popper-class="profile-select-popper"
                v-loading="profilesLoading"
                @change="applyProfileDefaults"
              >
                <el-option v-for="p in profiles" :key="p.profile_id" :label="p.name" :value="p.profile_id">
                  <div class="profile-option">
                    <div class="profile-option__header">
                      <span class="profile-option__name">{{ p.name }}</span>
                      <span class="profile-option__id muted">{{ p.profile_id }}</span>
                      <el-tag v-if="p.requires_sandbox" size="small" type="warning">需 sandbox</el-tag>
                    </div>
                    <span class="profile-option__desc muted">{{ p.description }}</span>
                    <div class="profile-option__detail">
                      <el-tag v-for="lane in profileLaneLabels(p)" :key="`${p.profile_id}-${lane}`" size="small" effect="plain">{{ lane }}</el-tag>
                      <el-tag v-for="ds in p.intelligence_datasets || []" :key="ds" size="small" effect="plain">{{ datasetMap[ds]?.pretty_name || ds }}</el-tag>
                      <span class="muted">limit={{ p.intelligence_limit ?? '不限' }}</span>
                    </div>
                  </div>
                </el-option>
              </el-select>
              <div v-if="selectedProfile" class="profile-summary">
                <div class="profile-summary__header">
                  <strong>{{ selectedProfile.name }}</strong>
                  <span class="muted">{{ selectedProfile.description }}</span>
                </div>
                <div class="profile-summary__row">
                  <span class="profile-summary__label">评测线</span>
                  <el-tag v-for="lane in profileLaneLabels(selectedProfile)" :key="lane" size="small" effect="plain">{{ lane }}</el-tag>
                </div>
                <div v-if="selectedProfile.run_intelligence !== false" class="profile-summary__row">
                  <span class="profile-summary__label">能力数据集</span>
                  <el-tag v-for="ds in profileDatasetLabels(selectedProfile)" :key="ds" size="small" type="primary" effect="plain">{{ ds }}</el-tag>
                  <span class="muted">limit={{ selectedProfile.intelligence_limit ?? '不限' }}</span>
                </div>
                <div v-if="selectedProfile.run_stress !== false" class="profile-summary__row">
                  <span class="profile-summary__label">压测默认</span>
                  <span>{{ profileStressDatasetName(selectedProfile) }}</span>
                  <span class="muted">parallel={{ profileListValue(selectedProfile.stress_options?.parallel) }}</span>
                  <span class="muted">number={{ profileListValue(selectedProfile.stress_options?.number) }}</span>
                </div>
                <div v-if="selectedProfile.requires_sandbox" class="profile-summary__row">
                  <span class="profile-summary__label">运行要求</span>
                  <el-tag size="small" type="warning">需要 EvalScope sandbox</el-tag>
                  <el-button size="small" :loading="sandboxTesting" @click="testSandbox">测试 Sandbox</el-button>
                  <el-tag :type="healthTagType(sandboxHealth?.status)" size="small" effect="plain">{{ sandboxHealth?.status || '未测试' }}</el-tag>
                  <span class="muted">{{ healthMessage(sandboxHealth) }}</span>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="评测线选择">
              <el-checkbox v-model="form.runGateway">基础评测</el-checkbox>
              <el-checkbox v-model="form.runStress">压测评测</el-checkbox>
              <el-checkbox v-model="form.runIntelligence">能力评测</el-checkbox>
            </el-form-item>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="执行时间">
                  <el-time-picker v-model="form.timeOfDay" format="HH:mm" value-format="HH:mm" class="full-width" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="间隔天数">
                  <el-input-number v-model="form.intervalDays" :min="1" :max="365" class="full-width" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <el-switch v-model="form.runOnce" active-text="仅执行一次" inactive-text="重复执行" />
            </el-form-item>
            <el-form-item v-if="form.runOnce" label="执行日期">
              <el-date-picker v-model="form.runDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" class="full-width" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="能力评测" name="intelligence" :disabled="!form.runIntelligence">
          <el-alert type="info" :closable="false" title="这里只展示本地已存在的数据集；有子集的数据集可展开自定义。" />
          <el-form label-position="top" class="mt">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="limit">
                  <el-input v-model="form.intelligenceLimit" placeholder="留空=不限" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="batch_size">
                  <el-input v-model="form.intelligenceEvalBatchSize" placeholder="默认" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <el-checkbox-group v-model="chosenDatasets" v-loading="datasetsLoading" class="dataset-pick-list">
            <el-empty v-if="!datasetsLoading && !localDatasetEntries.length" description="未发现本地能力评测数据集" />
            <div v-for="[name, meta] in localDatasetEntries" :key="name" class="dataset-pick">
              <el-card class="dataset-card" :class="{ 'dataset-card--active': chosenDatasets.includes(name) }" shadow="never">
                <div class="dataset-head">
                  <el-checkbox :value="name" :label="meta.pretty_name || name" />
                  <div class="dataset-head__tags">
                    <el-tag v-if="defaultDatasets.includes(name)" size="small" type="success">默认</el-tag>
                    <el-tag v-if="meta.needs_judge" size="small" type="warning" effect="plain">Judge</el-tag>
                  </div>
                </div>
                <p class="dataset-card__desc muted">{{ meta.description || '暂无描述' }}</p>
                <div class="dataset-card__meta muted">{{ profileDatasetDetail(name) }}</div>
                <div class="tag-row" v-if="meta.categories?.length">
                  <el-tag v-for="c in meta.categories" :key="c" size="small" effect="plain">{{ c }}</el-tag>
                </div>

                <el-collapse v-if="hasSubsets(meta)">
                  <el-collapse-item :title="subsetTitle(meta)" name="subsets">
                    <div class="subset-summary">
                      <div v-if="meta.configured_subset_list?.length" class="subset-line">
                        <span class="subset-label">默认运行</span>
                        <div class="subset-tags">
                          <el-tag v-for="s in meta.configured_subset_list" :key="`cfg-${name}-${s}`" type="primary" effect="plain" size="small">{{ s }}</el-tag>
                        </div>
                      </div>
                      <div class="subset-line subset-line--select">
                        <el-switch :model-value="!!subsetOverride[name]" @change="toggleSubsetOverride(name)" active-text="自定义子集" inactive-text="默认子集" size="small" />
                      </div>
                      <div v-if="subsetOverride[name]" class="subset-line">
                        <el-checkbox-group v-model="chosenSubsets[name]">
                          <el-checkbox v-for="s in meta.subsets" :key="`${name}-chk-${s}`" :value="s" :label="s" size="small" />
                        </el-checkbox-group>
                      </div>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </el-card>
            </div>
          </el-checkbox-group>
        </el-tab-pane>

        <el-tab-pane label="压测评测" name="stress" :disabled="!form.runStress">
          <el-alert type="info" :closable="false" title="只展示本地可解析的压测数据集；高级路径覆盖默认折叠为可选输入。" />
          <el-alert v-if="!stressDatasetsLoading && !stressDatasetList.length" class="mt" type="warning" :closable="false" title="未发现本地压测数据集，请先准备数据集后再创建压测定时任务。" />
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

          <el-form label-position="top">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="parallel">
                  <el-input v-model="form.stressParallel" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="number">
                  <el-input v-model="form.stressNumber" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="stream">
              <el-select v-model="form.stressStream" class="full-width">
                <el-option label="默认" value="" />
                <el-option label="true" value="true" />
                <el-option label="false" value="false" />
              </el-select>
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="最小 token">
                  <el-input v-model="form.stressMinTokens" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最大 token">
                  <el-input v-model="form.stressMaxTokens" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-collapse>
              <el-collapse-item title="高级：自定义 dataset_path" name="dataset-path">
                <el-form-item label="dataset_path（可选）">
                  <el-input
                    v-model="form.stressDatasetPath"
                    :placeholder="selectedStressDataset ? `留空使用上方选择：${selectedStressDataset}` : '留空自动解析'"
                  />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="确认创建" name="confirm">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="任务名称">{{ form.name || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="模型">{{ form.model_id || store.currentId || '未选择' }}</el-descriptions-item>
            <el-descriptions-item label="Profile">{{ selectedProfile?.name || form.profile }}</el-descriptions-item>
            <el-descriptions-item label="评测线">
              <el-tag v-if="form.runGateway" size="small" effect="plain">基础</el-tag>
              <el-tag v-if="form.runStress" size="small" effect="plain">压测</el-tag>
              <el-tag v-if="form.runIntelligence" size="small" effect="plain">能力</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="form.runIntelligence" label="能力数据集">
              <div class="subset-tags">
                <el-tag v-for="item in chosenDatasetMetas" :key="item.name" size="small" type="primary" effect="plain">
                  {{ item.meta.pretty_name || item.name }}
                </el-tag>
              </div>
            </el-descriptions-item>
            <el-descriptions-item v-if="form.runStress" label="压测数据集">
              {{ stressDatasets[selectedStressDataset]?.pretty_name || selectedStressDataset || '未选择' }}
            </el-descriptions-item>
            <el-descriptions-item label="运行时间">
              <span v-if="form.runOnce">{{ form.runDate || '未选择日期' }} {{ form.timeOfDay }}</span>
              <span v-else>每 {{ form.intervalDays }} 天 {{ form.timeOfDay }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="closeDrawer">取消</el-button>
        <el-button @click="resetForm">重置</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建定时任务</el-button>
      </div>
    </template>
  </el-drawer>
</template>
