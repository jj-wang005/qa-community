<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()
// Render text through Vue interpolation, never as untrusted HTML.
const parts = computed(() => props.content.split(/(```[\s\S]*?```)/g).filter(Boolean).map(text => ({
  code: text.startsWith('```'),
  text: text.startsWith('```') ? text.replace(/^```[^\n]*\n?/, '').replace(/```$/, '') : text,
})))
const sources = computed(() => [...new Set(Array.from(
  props.content.replace(/\*\*/g, '').matchAll(/(?:问题\s*(?:ID|编号|[＃#])|qid)\s*(?:为|是|[:：=])?\s*(\d+)/gi),
  match => Number(match[1]),
))].filter(id => Number.isSafeInteger(id) && id > 0))
</script>

<template>
  <div class="chat-content">
    <template v-for="(part, index) in parts" :key="index">
      <pre v-if="part.code"><code>{{ part.text }}</code></pre>
      <p v-else><template v-for="(text, i) in part.text.split(/(\*\*[^*\n]+\*\*)/g)" :key="i"><strong v-if="text.startsWith('**') && text.endsWith('**')">{{ text.slice(2, -2) }}</strong><template v-else>{{ text }}</template></template></p>
    </template>
    <nav v-if="sources.length" class="source-links" aria-label="回答中提及的问题"><RouterLink v-for="id in sources" :key="id" :to="`/questions/${id}`">查看问题 #{{ id }}</RouterLink></nav>
  </div>
</template>
