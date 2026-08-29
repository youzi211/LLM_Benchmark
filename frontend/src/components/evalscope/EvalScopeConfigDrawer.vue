<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useModelsStore } from "@/stores/models";
import {
  fetchEvalScopeConfig,
  fetchJudgeHealth,
  fetchSandboxHealth,
  saveEvalScopeConfig,
  type EvalScopeConfig,
  type EvalScopeHealthStatus,
} from "@/api/evaluations";
import ModelCreateDrawer from "@/components/models/ModelCreateDrawer.vue";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
}>();

const store = useModelsStore();
const loading = ref(false);
const saving = ref(false);
const sandboxTesting = ref(false);
const judgeTesting = ref(false);
const modelDrawerVisible = ref(false);
const sandboxHealth = ref<EvalScopeHealthStatus | null>(null);
const judgeHealth = ref<EvalScopeHealthStatus | null>(null);

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

function defaultForm() {
  return {
    judge_model_config_id: "",
    judge_worker_num: 5,
    judge_temperature: "0",
    judge_max_tokens: "4096",
    sandbox_enabled: false,
    sandbox_type: "docker",
    sandbox_base_url: "",
    datasets_dir: "",
    outputs_dir: "",
  };
}

const form = ref(defaultForm());

function healthTagType(status?: string) {
  if (status === "ok") return "success";
  if (status === "missing" || status === "warning") return "warning";
  if (status === "disabled" || status === "unknown") return "info";
  if (status === "error") return "danger";
  return "info";
}

function formatLatency(ms?: number | null) {
  if (ms === undefined || ms === null) return "-";
  return `${ms} ms`;
}

function formatHttpStatus(code?: number | null) {
  if (code === undefined || code === null) return "-";
  return String(code);
}

function formatHealthDetail(health: EvalScopeHealthStatus | null) {
  if (!health) return "";
  if (typeof health.error === "string") return health.error;
  if (health.error && typeof health.error === "object") return JSON.stringify(health.error);
  if (health.message) return health.message;
  return "";
}

function formatConfigured(c?: boolean | null) {
  if (c === true) return "已配置";
  if (c === false) return "未配置";
  return "-";
}

function healthMessage(health: EvalScopeHealthStatus | null) {
  if (!health) return "尚未测试";
  const parts: string[] = [];
  parts.push(health.status || "");
  if (health.latency_ms != null) parts.push(`${health.latency_ms} ms`);
  if (health.http_status != null) parts.push(`HTTP ${health.http_status}`);
  if (health.checked_url) parts.push(health.checked_url);
  if (health.base_url && health.base_url !== health.checked_url) parts.push(health.base_url);
  return parts.filter(Boolean).join(" · ");
}

function toOptionalPositiveInteger(raw: string, field: string) {
  const text = String(raw || "").trim();
  if (!text) return undefined;
  const value = Number(text);
  if (!Number.isInteger(value) || value < 1) throw new Error(`${field} 必须是正整数`);
  return value;
}

function toNumberOrDefault(raw: string, fallback: number) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  const value = Number(text);
  if (!Number.isFinite(value)) throw new Error("Judge temperature 必须是数字");
  return value;
}

function applyConfig(config: EvalScopeConfig) {
  form.value.judge_model_config_id = config.judge_model_config_id || "";
  form.value.judge_worker_num = config.judge_worker_num || 5;
  form.value.judge_temperature = String(config.judge_generation_config?.temperature ?? 0);
  form.value.judge_max_tokens = String(config.judge_generation_config?.max_tokens ?? 4096);
  form.value.sandbox_enabled = Boolean(config.sandbox_enabled);
  form.value.sandbox_type = config.sandbox_type || "docker";
  const manager = config.sandbox_manager_config || {};
  const baseUrl = manager.base_url || manager.url || manager.endpoint;
  form.value.sandbox_base_url = typeof baseUrl === "string" && baseUrl !== "***" ? baseUrl : "";
  form.value.datasets_dir = config.datasets_dir || "";
  form.value.outputs_dir = config.outputs_dir || "";
}

async function loadConfig() {
  loading.value = true;
  try {
    await store.load();
    applyConfig(await fetchEvalScopeConfig());
  } finally {
    loading.value = false;
  }
}

function buildPayload(): EvalScopeConfig {
  const judgeMaxTokens = toOptionalPositiveInteger(form.value.judge_max_tokens, "Judge max_tokens") ?? 4096;
  const payload: EvalScopeConfig = {
    judge_model_config_id: form.value.judge_model_config_id || null,
    judge_generation_config: {
      temperature: toNumberOrDefault(form.value.judge_temperature, 0),
      max_tokens: judgeMaxTokens,
    },
    judge_worker_num: form.value.judge_worker_num,
    sandbox_enabled: form.value.sandbox_enabled,
    sandbox_type: form.value.sandbox_type || "docker",
    sandbox_manager_config: {},
    datasets_dir: form.value.datasets_dir.trim() || null,
    outputs_dir: form.value.outputs_dir.trim() || null,
  };
  const sandboxBaseUrl = form.value.sandbox_base_url.trim();
  if (sandboxBaseUrl) payload.sandbox_manager_config = { base_url: sandboxBaseUrl };
  return payload;
}

async function saveConfig() {
  saving.value = true;
  try {
    const saved = await saveEvalScopeConfig(buildPayload());
    applyConfig(saved);
    ElMessage.success("评测环境配置已保存");
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    saving.value = false;
  }
}

async function testSandbox() {
  sandboxTesting.value = true;
  sandboxHealth.value = null;
  try {
    await saveEvalScopeConfig(buildPayload());
    sandboxHealth.value = await fetchSandboxHealth(true);
    if (sandboxHealth.value.status === "ok") ElMessage.success("Sandbox 可用");
    else ElMessage.warning(`Sandbox 状态：${sandboxHealth.value.status}`);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    sandboxTesting.value = false;
  }
}

async function testJudge() {
  judgeTesting.value = true;
  judgeHealth.value = null;
  try {
    await saveEvalScopeConfig(buildPayload());
    judgeHealth.value = await fetchJudgeHealth();
    if (judgeHealth.value.status === "ok") ElMessage.success("Judge 模型可用");
    else ElMessage.warning(`Judge 状态：${judgeHealth.value.status}`);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    judgeTesting.value = false;
  }
}

function onJudgeModelCreated(id: string) {
  form.value.judge_model_config_id = id;
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void loadConfig();
  },
);
</script>

<template>
  <el-drawer v-model="visible" title="评测环境配置" size="640px" class="evalscope-config-drawer">
    <div v-loading="loading">
      <el-alert
        type="info"
        :closable="false"
        title="Judge 用于 LLM-as-Judge 数据集评分；Sandbox 用于 HumanEval、MBPP、LiveCodeBench 等代码执行类数据集。"
      />

      <div v-if="store.currentModel" class="current-model-bar">
        <span class="label">当前模型</span>
        <strong>{{ store.currentModel.name || store.currentModel.id }}</strong>
        <span class="muted">{{ store.currentModel.id }}</span>
        <span class="muted env-url">{{ store.currentModel.base_url || '' }}</span>
      </div>
      <div v-else class="current-model-bar current-model-bar--empty">
        <span class="label">当前模型</span>
        <span class="muted">尚未选择模型。先到顶部选择模型后再配置 Judge / Sandbox。</span>
      </div>

      <el-form label-position="top" class="evalscope-config-form">
        <div class="section-title">Judge 模型</div>
        <el-form-item label="Judge 模型配置">
          <div class="inline-control-row">
            <el-select v-model="form.judge_model_config_id" clearable placeholder="使用默认 analysis_model 或选择模型" class="full-width" :loading="store.loading">
              <el-option label="使用默认 analysis_model" value="" />
              <el-option v-for="m in store.models" :key="m.id" :label="m.name ?? m.model ?? m.id" :value="m.id">
                <span>{{ m.name ?? m.model ?? m.id }}</span>
                <span class="muted option-side">{{ m.id }}</span>
              </el-option>
            </el-select>
            <el-button @click="modelDrawerVisible = true">新增模型</el-button>
          </div>
          <div class="form-help">建议为 Judge 单独配置稳定、低温度的模型。未选择时会回退到 data/models.json 的 analysis_model_id。</div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Judge worker 数">
              <el-input-number v-model="form.judge_worker_num" :min="1" :max="128" class="full-width" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Judge max_tokens">
              <el-input v-model="form.judge_max_tokens" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="Judge temperature">
          <el-input v-model="form.judge_temperature" />
        </el-form-item>
        <div class="health-row">
          <el-button :loading="judgeTesting" @click="testJudge">测试 Judge</el-button>
          <el-tag :type="healthTagType(judgeHealth?.status)" effect="plain">{{ judgeHealth?.status || '未测试' }}</el-tag>
          <span class="muted">{{ healthMessage(judgeHealth) }}</span>
        </div>
        <el-descriptions v-if="judgeHealth" :column="3" size="small" border class="mt health-detail">
          <el-descriptions-item label="延迟">{{ formatLatency(judgeHealth.latency_ms) }}</el-descriptions-item>
          <el-descriptions-item label="HTTP">{{ formatHttpStatus(judgeHealth.http_status) }}</el-descriptions-item>
          <el-descriptions-item label="模型配置">{{ judgeHealth.model_config_id || judgeHealth.model_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="URL">{{ judgeHealth.checked_url || judgeHealth.base_url || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ judgeHealth.source || 'auto' }}</el-descriptions-item>
          <el-descriptions-item label="说明">
            <code class="health-error">{{ formatHealthDetail(judgeHealth) }}</code>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />
        <div class="section-title">Sandbox</div>
        <el-form-item>
          <el-switch v-model="form.sandbox_enabled" active-text="启用 Sandbox" inactive-text="关闭 Sandbox" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Sandbox 类型">
              <el-input v-model="form.sandbox_type" placeholder="docker" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="远端 Sandbox Base URL">
              <el-input v-model="form.sandbox_base_url" placeholder="如：http://10.182.17.2:1234" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-help">如果留空，则对 docker 类型执行本机 docker daemon 检测；填写 URL 时会优先测试远端服务连通性。</div>
        <div class="health-row">
          <el-button :loading="sandboxTesting" @click="testSandbox">测试 Sandbox</el-button>
          <el-tag :type="healthTagType(sandboxHealth?.status)" effect="plain">{{ sandboxHealth?.status || '未测试' }}</el-tag>
          <span class="muted">{{ healthMessage(sandboxHealth) }}</span>
        </div>
        <el-descriptions v-if="sandboxHealth" :column="3" size="small" border class="mt health-detail">
          <el-descriptions-item label="延迟">{{ formatLatency(sandboxHealth.latency_ms) }}</el-descriptions-item>
          <el-descriptions-item label="HTTP">{{ formatHttpStatus(sandboxHealth.http_status) }}</el-descriptions-item>
          <el-descriptions-item label="配置">{{ formatConfigured(sandboxHealth.configured) }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ sandboxHealth.engine || sandboxHealth.mode || '-' }}</el-descriptions-item>
          <el-descriptions-item label="探测 URL">{{ sandboxHealth.checked_url || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Base URL">{{ sandboxHealth.base_url || '-' }}</el-descriptions-item>
          <el-descriptions-item label="说明" :span="3">
            <code class="health-error">{{ formatHealthDetail(sandboxHealth) || '沙箱已就绪' }}</code>
          </el-descriptions-item>
        </el-descriptions>

        <el-collapse class="mt">
          <el-collapse-item title="高级：EvalScope 路径" name="paths">
            <el-form-item label="datasets_dir">
              <el-input v-model="form.datasets_dir" placeholder="留空使用默认 data/evalscope_datasets" />
            </el-form-item>
            <el-form-item label="outputs_dir">
              <el-input v-model="form.outputs_dir" placeholder="留空使用默认 outputs/evalscope" />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="visible = false">关闭</el-button>
        <el-button :loading="sandboxTesting" @click="testSandbox">测试 Sandbox</el-button>
        <el-button :loading="judgeTesting" @click="testJudge">测试 Judge</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
      </div>
    </template>

    <ModelCreateDrawer v-model="modelDrawerVisible" @created="onJudgeModelCreated" />
  </el-drawer>
</template>
