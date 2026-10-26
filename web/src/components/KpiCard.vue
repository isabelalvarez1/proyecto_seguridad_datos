<script setup>
defineProps({ label: String, value: String, detail: String, tone: { type: String, default: 'blue' } })
</script>
<template><section class="kpi-card" :class="'kpi-' + tone"><p class="kpi-label">{{ label }}</p><p class="kpi-value">{{ value }}</p><p class="kpi-detail">{{ detail }}</p></section></template>
