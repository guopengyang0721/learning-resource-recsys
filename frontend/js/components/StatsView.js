/** 数据看板（管理员）：核心统计 + 离线指标 + 分类/行为分布图 + 热门Top10 + 最近行为流水 */
(function () {
  const { nextTick } = window.Vue;
  const C = window.App.components = window.App.components || {};
  let chartOffline = null, chartCat = null, chartAct = null;

  function render(st) {
    if (!st) return;
    nextTick(() => {
      const names = { user_cf: 'User-based CF', item_cf: 'Item-based CF', svd: 'SVD' };
      // AdminView 的 v-if 子页切换会重建图表容器 DOM：
      // 模块级旧实例绑定的画布已脱离文档，必须 getDom 检测后 dispose 重建
      const rebind = (inst, el) => {
        if (inst && inst.getDom() !== el) { inst.dispose(); inst = null; }
        return inst || echarts.init(el);
      };
      // 离线指标柱状图
      const el1 = document.getElementById('chart');
      if (el1 && window.echarts) {
        chartOffline = rebind(chartOffline, el1);
        const m = (st.offline_metrics && st.offline_metrics.results) || null;
        if (m) {
          const algos = Object.keys(m);
          chartOffline.setOption({
            title: { text: '离线评估对比（Top-10）', left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            legend: { data: ['Precision@10', 'Recall@10', 'Coverage@10'], top: 28 },
            grid: { top: 80, bottom: 30 },
            xAxis: { type: 'category', data: algos.map(a => names[a] || a) },
            yAxis: { type: 'value', max: 1 },
            series: [
              { name: 'Precision@10', type: 'bar', data: algos.map(a => m[a].precision) },
              { name: 'Recall@10', type: 'bar', data: algos.map(a => m[a].recall) },
              { name: 'Coverage@10', type: 'bar', data: algos.map(a => m[a].coverage) }
            ]
          });
        }
      }
      // 分类分布饼图
      const el2 = document.getElementById('chart-cat');
      if (el2 && window.echarts && st.category_dist) {
        chartCat = rebind(chartCat, el2);
        chartCat.setOption({
          title: { text: '在线资源分类分布', left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'item' },
          series: [{ type: 'pie', radius: ['32%', '62%'], center: ['50%', '56%'],
                     data: Object.entries(st.category_dist).map(([name, value]) => ({ name, value })) }]
        });
      }
      // 行为类型占比
      const el3 = document.getElementById('chart-act');
      if (el3 && window.echarts && st.action_count) {
        chartAct = rebind(chartAct, el3);
        const names2 = { view: '浏览', favorite: '收藏', rate: '评分', download: '下载' };
        chartAct.setOption({
          title: { text: '行为类型占比', left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'item' },
          series: [{ type: 'pie', radius: ['32%', '62%'], center: ['50%', '56%'],
                     data: Object.entries(st.action_count).map(([k, v]) => ({ name: names2[k] || k, value: v })) }]
        });
      }
    });
  }

  C.StatsView = {
    setup() {
      const { watch, nextTick, onBeforeUnmount, ref } = window.Vue;
      const { state, loadStats } = window.App.store;
      const A = window.App.api;
      // 近 7 天趋势（独立接口，与看板统计分离）
      const trend = ref(null);
      let trendChart = null;

      async function loadTrend() {
        try {
          trend.value = await A.trend();
          nextTick(renderTrend);
        } catch (e) { /* 趋势加载失败静默 */ }
      }
      function renderTrend() {
        const el = document.getElementById('trend-chart');
        if (!el || !window.echarts || !trend.value) return;
        if (trendChart && trendChart.getDom() !== el) { trendChart.dispose(); trendChart = null; }
        trendChart = trendChart || echarts.init(el);
        trendChart.setOption({
          title: { text: '近 7 天系统活跃趋势', left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          legend: { data: ['新增行为', '活跃用户'], top: 28 },
          grid: { left: 50, right: 24, top: 64, bottom: 30 },
          xAxis: { type: 'category', data: trend.value.days.map(d => d.date) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            { name: '新增行为', type: 'line', smooth: true,
              data: trend.value.days.map(d => d.behaviors),
              areaStyle: { opacity: .2 }, itemStyle: { color: '#409eff' } },
            { name: '活跃用户', type: 'line', smooth: true,
              data: trend.value.days.map(d => d.users),
              itemStyle: { color: '#67c23a' } },
          ],
        });
      }

      // 看板数据整体替换（引用变化）必触发重绘——这是图表渲染的唯一数据入口
      watch(() => state.stats, (v) => render(v));
      // 窗口缩放时让图表自适应
      const onResize = () => [chartOffline, chartCat, chartAct, trendChart].forEach(c => c && c.resize());
      window.addEventListener('resize', onResize);
      // 组件卸载（切走管理后台）：释放图表实例并解绑监听，避免泄漏
      onBeforeUnmount(() => {
        window.removeEventListener('resize', onResize);
        [chartOffline, chartCat, chartAct, trendChart].forEach(c => { if (c) { c.dispose(); } });
        chartOffline = chartCat = chartAct = trendChart = null;
      });
      return { s: state, loadStats, trend, loadTrend };
    },
    mounted() {
      this.loadStats();
      this.loadTrend();
      // 从「资源管理/用户管理」子页切回时 stats 已有旧值，watch 不会触发 → 手动补画一次
      this.$nextTick(() => { if (this.s.stats) render(this.s.stats); });
    },
    template: `
    <div>
      <el-row :gutter="12">
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="用户数" :value="s.stats ? s.stats.users : 0"></el-statistic></el-card></el-col>
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="在线资源" :value="s.stats ? s.stats.resources : 0"></el-statistic></el-card></el-col>
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="评分记录" :value="s.stats ? s.stats.scores : 0"></el-statistic></el-card></el-col>
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="待审核资源" :value="s.stats ? (s.stats.pending_cnt || 0) : 0"></el-statistic></el-card></el-col>
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="禁用账号" :value="s.stats ? (s.stats.disabled_cnt || 0) : 0"></el-statistic></el-card></el-col>
        <el-col :xs="12" :sm="8" :md="4"><el-card shadow="hover"><el-statistic title="矩阵密度 %" :value="s.stats ? s.stats.matrix_density : 0"></el-statistic></el-card></el-col>
      </el-row>

      <el-row :gutter="12" style="margin-top:12px">
        <el-col :xs="24" :md="16"><el-card><div id="chart" style="width:100%;height:320px"></div></el-card></el-col>
        <el-col :xs="24" :md="8"><el-card><div id="chart-cat" style="width:100%;height:320px"></div></el-card></el-col>
      </el-row>
      <el-row :gutter="12" style="margin-top:12px">
        <el-col :xs="24" :md="8"><el-card><div id="chart-act" style="width:100%;height:300px"></div></el-card></el-col>
        <el-col :xs="24" :md="16">
          <el-card header="🔥 热门资源 Top10（按点击）">
            <el-table :data="s.stats ? s.stats.top_resources : []" size="small" max-height="260">
              <el-table-column type="index" label="#" width="50"></el-table-column>
              <el-table-column prop="title" label="资源" min-width="200"></el-table-column>
              <el-table-column prop="category" label="分类" width="100"></el-table-column>
              <el-table-column prop="click_count" label="点击" width="80"></el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="12" style="margin-top:12px">
        <el-col :span="24">
          <el-card><div id="trend-chart" style="width:100%;height:260px"></div></el-card>
        </el-col>
      </el-row>

      <el-card header="📜 最近行为流水（最新 30 条）" style="margin-top:12px">
        <el-table :data="s.stats ? s.stats.recent_logs : []" size="small" max-height="320">
          <el-table-column prop="time" label="时间" width="110"></el-table-column>
          <el-table-column prop="user" label="用户" width="120"></el-table-column>
          <el-table-column prop="title" label="资源" min-width="220"></el-table-column>
          <el-table-column label="行为" width="90">
            <template #default="scope">
              <el-tag size="small"
                      :type="scope.row.action==='rate' ? 'warning' : (scope.row.action==='favorite' ? 'success' : 'info')">
                {{ scope.row.action_name || scope.row.action }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>`
  };
})();
