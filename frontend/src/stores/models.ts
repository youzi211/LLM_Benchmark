import { defineStore } from "pinia";
import { createModel, fetchModels, type ModelConfig, type ModelConfigCreate } from "@/api/models";

interface State {
  models: ModelConfig[];
  currentId: string | null;
  loading: boolean;
  error: string | null;
}

export const useModelsStore = defineStore("models", {
  state: (): State => ({
    models: [],
    currentId: null,
    loading: false,
    error: null,
  }),
  getters: {
    currentModel(state): ModelConfig | null {
      return state.models.find((m) => m.id === state.currentId) ?? null;
    },
  },
  actions: {
    async load(force = false): Promise<void> {
      if (!force && this.models.length) return;
      this.loading = true;
      this.error = null;
      try {
        const models = await fetchModels();
        this.models = models;
        if (this.currentId && !models.some((model) => model.id === this.currentId)) {
          this.currentId = null;
        }
        if (!this.currentId && models.length) {
          this.currentId = models[0].id ?? null;
        }
      } catch (err) {
        this.error = err instanceof Error ? err.message : String(err);
      } finally {
        this.loading = false;
      }
    },
    select(id: string): void {
      this.currentId = id;
    },
    async create(payload: ModelConfigCreate): Promise<ModelConfig> {
      const created = await createModel(payload);
      await this.load(true);
      this.currentId = created.id;
      return created;
    },
  },
});
