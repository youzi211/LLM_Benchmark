<script setup lang="ts">
import StatusTag from "@/components/common/StatusTag.vue";
import { displayStatus, type LaneResults } from "@/api/model-evaluations";
import { formatDate } from "@/utils/time";

defineProps<{ result: LaneResults }>();
</script>

<template>
  <div class="lane-execution">
    <div><span v-if="result.latest_attempt">最新执行：</span><StatusTag :status="result.latest_attempt?.status || 'unassessed'" :label="displayStatus(result.latest_attempt)" compact /></div>
    <p v-if="result.latest_success">最近成功证据：{{ formatDate(result.latest_success.completed_at) }}</p>
    <p v-else-if="result.partial_result">部分证据可用：{{ formatDate(result.partial_result.completed_at) }}</p>
    <p v-else-if="result.latest_attempt">尚无成功证据</p>
  </div>
</template>

<style scoped>
.lane-execution { font-size: 12px; line-height: 1.8; }
.lane-execution p { margin: 6px 0 0; color: var(--lb-muted); font-size: 11px; overflow-wrap: anywhere; }
</style>
