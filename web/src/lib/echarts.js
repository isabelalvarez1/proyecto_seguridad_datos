import { use, init, registerMap } from 'echarts/core'
import { LineChart, BarChart, PieChart, ScatterChart, HeatmapChart, MapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, GraphicComponent, AriaComponent, GeoComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, BarChart, PieChart, ScatterChart, HeatmapChart, MapChart, GridComponent, TooltipComponent,
  LegendComponent, VisualMapComponent, GraphicComponent, AriaComponent, GeoComponent, CanvasRenderer])
export { init, registerMap }
