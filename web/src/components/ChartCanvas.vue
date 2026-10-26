<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from '../lib/echarts.js'
const props = defineProps({ option: Object, title: String, height: { type: Number, default: 330 } })
const emit = defineEmits(['select'])
const element = ref(null)
let chart, observer
onMounted(() => {
  chart = echarts.init(element.value)
  chart.setOption(props.option || {}, true)
  chart.on('click', event => emit('select', event))
  observer = new ResizeObserver(() => chart?.resize()); observer.observe(element.value)
})
watch(() => props.option, value => chart?.setOption(value || {}, true), { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
function exportImage(lines = []) {
  if (!chart) return
  const image = new Image()
  image.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = image.width; canvas.height = image.height + 75 + lines.length * 28
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#18375d'; ctx.font = 'bold 25px sans-serif'
    ctx.fillText(props.title || 'Figura', 25, 35, canvas.width - 50)
    ctx.drawImage(image, 0, 55)
    ctx.fillStyle = '#60748d'; ctx.font = '17px sans-serif'
    lines.forEach((line, index) => ctx.fillText(line, 25, image.height + 80 + index * 28, canvas.width - 50))
    const link = document.createElement('a'); link.href = canvas.toDataURL('image/png')
    link.download = (props.title || 'figura').replace(/[^\p{L}\p{N}_-]/gu, '_') + '.png'; link.click()
  }
  image.src = chart.getDataURL({ pixelRatio: 2, backgroundColor: '#fff' })
}
defineExpose({ exportImage })
</script>
<template><div ref="element" class="chart-canvas" :style="{ height: height + 'px' }" role="img" :aria-label="title" /></template>
