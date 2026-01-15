<template>
  <div class="markdown-body" v-html="renderedContent"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const props = defineProps<{
  content: string;
}>();

const renderedContent = computed(() => {
  const html = marked.parse(props.content || '');
  return DOMPurify.sanitize(html as string);
});
</script>

<style>
/* 简单的 Markdown 样式，实际项目中可能需要更完善的 CSS */
.markdown-body pre {
  background-color: #f6f8fa;
  border-radius: 6px;
  padding: 16px;
  overflow: auto;
}
.markdown-body code {
  font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
}
</style>
