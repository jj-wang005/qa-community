<script setup lang="ts">
import { MessageSquareText } from 'lucide-vue-next'
defineProps<{ title: string; description: string }>()
</script>
<template><div class="empty-state"><MessageSquareText :size="30" /><strong>{{ title }}</strong><p>{{ description }}</p></div></template>
