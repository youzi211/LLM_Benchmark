import { defineStore } from "pinia";
import { createModel, deleteModel, fetchModels, updateModel, type ModelConfig, type ModelConfigCreate, type ModelConfigUpdate } from "@/api/models";
import { createSingleFlight } from "@/utils/singleFlight";

const fetchModelsSingleFlight = createSingleFlight(fetchModels);

interface State {
  models: ModelConfig[];
  currentId: string | null;
  loading: boolean;
  error: string | null;
  loadVersion: number;
}

export const useModelsStore = defineStore("models", {
  state: (): State => ({
    models: [],
    currentId: null,
    loading: false,
    error: null,
    loadVersion: 0,
  }),
  getters: {
    currentModel(state): ModelConfig | null {
      return state.models.find((m) => m.id === state.currentId) ?? null;
    },
  },
  actions: {
    async load(force = false): Promise<void> {
      if (!force && this.models.length) return;
      const loadVersion = ++this.loadVersion;
      this.loading = true;
      this.error = null;
      try {
        const models = force ? await fetchModels() : await fetchModelsSingleFlight();
        if (loadVersion !== this.loadVersion) return;
        this.models = models;
        if (this.currentId && !models.some((model) => model.id === this.currentId)) {
          this.currentId = null;
        }
        if (!this.currentId && models.length) {
          this.currentId = models[0].id ?? null;
        }
      } catch (err) {
        if (loadVersion !== this.loadVersion) return;
        this.error = err instanceof Error ? err.message : String(err);
      } finally {
        if (loadVersion === this.loadVersion) this.loading = false;
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
    async update(id: string, patch: ModelConfigUpdate): Promise<ModelConfig> {
      const updated = await updateModel(id, patch);
      await this.load(true);
      return updated;
    },
    async remove(id: string): Promise<void> {
      await deleteModel(id);
      await this.load(true);
    },
  },
});
