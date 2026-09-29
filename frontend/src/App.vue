<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppShell from './components/AppShell.vue'
</script>

<template>
  <AppShell>
    <RouterView v-slot="{ Component }">
      <KeepAlive include="AssistantPage"><component :is="Component" /></KeepAlive>
    </RouterView>
  </AppShell>
</template>
