<script setup>
import { Info } from '@lucide/vue'
defineProps({ tone: { type: String, default: 'info' } })
</script>
<template><div class="status-banner" :class="tone" role="note"><Info :size="18" class="shrink-0 mt-0.5" /><div><slot /></div></div></template>
