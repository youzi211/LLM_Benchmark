<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useModelsStore } from "@/stores/models";
import type { ModelProtocol } from "@/api/models";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
  (event: "created", id: string): void;
}>();

const store = useModelsStore();
const submitting = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

function defaultForm() {
  return {
    id: "",
    name: "",
    protocol: "chat_completions" as ModelProtocol,
    base_url: "",
    api_key: "",
    model: "",
    timeout_seconds: 60,
    enabled: true,
    declared_context_tokens: "",
    declared_max_output_tokens: "",
    concurrency_levels: "1,5,10,20",
  };
}

const form = ref(defaultForm());

function slugify(value: string) {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 128);
}

function maybeFillId() {
  if (form.value.id.trim()) return;
  const source = form.value.name || form.value.model;
  const id = slugify(source);
  if (id) form.value.id = id;
}

function toOptionalPositiveInteger(raw: string, field: string) {
  const text = String(raw || "").trim();
  if (!text) return undefined;
  const value = Number(text);
  if (!Number.isInteger(value) || value < 1) throw new Error(`${field} 必须是正整数`);
  return value;
}

function parseConcurrency(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return [1, 5, 10, 20];
  const values = text.split(/[，,\s]+/).filter(Boolean).map(Number);
  if (!values.length) return [1, 5, 10, 20];
  if (values.some((item) => !Number.isInteger(item) || item < 1 || item > 200)) {
    throw new Error("并发等级只能包含 1-200 的正整数");
  }
  return Array.from(new Set(values)).sort((a, b) => a - b);
}

function validateRequired() {
  maybeFillId();
  if (!form.value.id.trim()) throw new Error("请填写模型 ID");
  if (!/^[a-zA-Z0-9_.-]+$/.test(form.value.id.trim())) throw new Error("模型 ID 只能包含字母、数字、下划线、点和横线");
  if (!form.value.name.trim()) throw new Error("请填写显示名称");
  if (!form.value.base_url.trim()) throw new Error("请填写 Base URL");
  if (!form.value.api_key.trim()) throw new Error("请填写 API Key");
  if (!form.value.model.trim()) throw new Error("请填写上游模型名称");
  if (!Number.isInteger(form.value.timeout_seconds) || form.value.timeout_seconds < 1 || form.value.timeout_seconds > 600) {
    throw new Error("超时时间必须在 1-600 秒之间");
  }
}

function buildPayload() {
  validateRequired();
  return {
    id: form.value.id.trim(),
    name: form.value.name.trim(),
    protocol: form.value.protocol,
    base_url: form.value.base_url.trim(),
    api_key: form.value.api_key.trim(),
    model: form.value.model.trim(),
    timeout_seconds: form.value.timeout_seconds,
    enabled: form.value.enabled,
    declared_context_tokens: toOptionalPositiveInteger(form.value.declared_context_tokens, "上下文窗口"),
    declared_max_output_tokens: toOptionalPositiveInteger(form.value.declared_max_output_tokens, "最大输出 tokens"),
    concurrency_levels: parseConcurrency(form.value.concurrency_levels),
  };
}

function resetForm() {
  form.value = defaultForm();
}

function closeDrawer() {
  visible.value = false;
}

async function submit() {
  submitting.value = true;
  try {
    const created = await store.create(buildPayload());
    ElMessage.success(`模型已添加：${created.name || created.id}`);
    emit("created", created.id);
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
    if (open) void store.load();
  },
);
</script>

<template>
  <el-drawer v-model="visible" title="添加模型" size="520px" class="model-editor-drawer" destroy-on-close>
    <el-alert
      class="model-editor__hint"
      type="warning"
      :closable="false"
      title="API Key 会写入本地 data/models.json，请确认不要提交该文件。列表接口只返回脱敏后的 key。"
    />

    <el-form label-position="top" class="model-editor-form">
      <el-form-item label="模型 ID">
        <el-input v-model="form.id" placeholder="如：ms-enclave-glm52" />
        <div class="form-help">唯一标识，只能包含字母、数字、下划线、点和横线。</div>
      </el-form-item>
      <el-form-item label="显示名称">
        <el-input v-model="form.name" placeholder="如：ms-enclave / GLM-5.2" @blur="maybeFillId" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="协议">
            <el-select v-model="form.protocol" class="full-width">
              <el-option label="Chat Completions" value="chat_completions" />
              <el-option label="Responses" value="responses" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="启用状态">
            <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Base URL">
        <el-input v-model="form.base_url" placeholder="如：http://10.182.17.2:1234/v1" />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="form.api_key" placeholder="请输入 API Key" show-password />
      </el-form-item>
      <el-form-item label="上游模型名称">
        <el-input v-model="form.model" placeholder="如：LKL-GLM-5.2-FP8" @blur="maybeFillId" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="超时时间（秒）">
            <el-input-number v-model="form.timeout_seconds" :min="1" :max="600" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="并发等级">
            <el-input v-model="form.concurrency_levels" placeholder="1,5,10,20" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-collapse>
        <el-collapse-item title="可选：声明模型能力" name="capability">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="上下文窗口 tokens">
                <el-input v-model="form.declared_context_tokens" placeholder="可选" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="最大输出 tokens">
                <el-input v-model="form.declared_max_output_tokens" placeholder="可选" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="closeDrawer">取消</el-button>
        <el-button @click="resetForm">重置</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">添加并选中</el-button>
      </div>
    </template>
  </el-drawer>
</template>
