/** 个性化推荐视图：算法切换、Top-N 推荐卡片（含理由）、热门资源冷启动兜底栏、三算法并排对比 */
(function () {
  const { ref } = window.Vue;
  const { ElMessage } = window.ElementPlus;
  const C = window.App.components = window.App.components || {};

  C.RecommendView = {
    setup() {
      const { state, loadRec, openDetail } = window.App.store;
      const A = window.App.api;
      // 三算法并排对比面板（局部状态，不入全局 store）
      const cmp = ref({ visible: false, loading: false, data: null });
      const SHORT_NAME = { user_cf: 'User-CF', item_cf: 'Item-CF', svd: 'SVD' };
      const ALGO_NAME = { user_cf: 'User-CF 协同过滤', item_cf: 'Item-CF 协同过滤', svd: 'SVD 隐语义模型' };

      async function toggleCompare() {
        if (cmp.value.visible) { cmp.value.visible = false; return; }
        cmp.value.visible = true;
        cmp.value.loading = true;
        try {
          cmp.value.data = await A.compareRecommend(8);
        } catch (e) {
          ElMessage.error('算法对比加载失败，请稍后重试');
          cmp.value.visible = false;
        } finally { cmp.value.loading = false; }
      }
      /** "user_cf|item_cf" → "User-CF ∩ Item-CF" */
      function pairName(key) {
        const [a, b] = key.split('|');
        return `${SHORT_NAME[a] || a} ∩ ${SHORT_NAME[b] || b}`;
      }
      return { s: state, loadRec, openDetail, cmp, toggleCompare, pairName, ALGO_NAME };
    },
    template: `
    <div>
      <div style="margin-bottom:12px;display:flex;gap:10px;align-items:center">
        <span>推荐算法：</span>
        <el-select v-model="s.algo" style="width:220px" @change="loadRec">
          <el-option label="User-based 协同过滤（主推）" value="user_cf"></el-option>
          <el-option label="Item-based 协同过滤（对比）" value="item_cf"></el-option>
          <el-option label="SVD 隐语义模型（进阶）" value="svd"></el-option>
        </el-select>
        <el-button type="primary" @click="loadRec" :loading="s.recLoading">刷新推荐</el-button>
        <el-tag type="info">{{ s.recSource }}</el-tag>
        <el-button type="warning" plain :loading="cmp.loading" @click="toggleCompare">📊 三算法并排对比</el-button>
      </div>

      <!-- 三算法并排对比面板 -->
      <el-card v-if="cmp.visible" shadow="never" style="margin-bottom:12px">
        <template #header>
          <b>📊 三种推荐算法结果对比</b>
          <span v-if="cmp.data && !cmp.data.known" style="color:#e6a23c;font-size:12px;margin-left:10px">
            当前行为较少，三种算法均为热门资源兜底
          </span>
        </template>
        <el-row :gutter="12" v-if="cmp.data">
          <el-col v-for="(a, key) in cmp.data.algos" :key="key" :xs="24" :md="8" style="margin-bottom:8px">
            <el-card shadow="hover" :body-style="{padding:'8px 12px'}">
              <template #header>
                <b style="font-size:13px">{{ a.name }}</b>
                <span style="color:#98a5bd;font-size:12px;float:right">{{ (a.items || []).length }} 条</span>
              </template>
              <div v-if="a.error" style="color:#e6a23c;font-size:12px;padding:8px 0">{{ a.error }}</div>
              <div v-for="(it, i) in a.items" :key="it.resource_id"
                   style="padding:5px 0;border-bottom:1px dashed #f0f0f0;cursor:pointer;font-size:13px"
                   @click="openDetail(it)">
                <span style="color:#98a5bd;margin-right:6px">{{ i + 1 }}.</span>{{ it.title }}
                <span style="color:#999;float:right">{{ it.score }}</span>
              </div>
              <el-empty v-if="!a.items.length && !a.error" description="无结果" :image-size="40"></el-empty>
            </el-card>
          </el-col>
        </el-row>
        <div v-if="cmp.data" style="margin-top:10px;color:#666;font-size:13px;line-height:2">
          📐 重合度分析：
          <el-tag v-for="(v, k) in cmp.data.overlap" :key="k" size="small" style="margin:0 8px 4px 0">
            {{ pairName(k) }} 重合 {{ v }} 条
          </el-tag>
          <div>三种算法共覆盖 <b style="color:#409eff">{{ cmp.data.unique_count }}</b> 个不同资源；
            模型训练时间：{{ cmp.data.model_time }}</div>
        </div>
      </el-card>
      <el-row :gutter="12">
        <el-col :span="16">
          <el-card v-for="item in s.recList" :key="item.resource_id" style="margin-bottom:10px"
                   @click="openDetail(item)" shadow="hover">
            <div style="display:flex;justify-content:space-between">
              <b>{{ item.title }}</b>
              <el-tag size="small" type="warning">预测评分 {{ item.score }}</el-tag>
            </div>
            <div style="color:#666;font-size:13px;margin:6px 0">
              <el-tag size="small">{{ item.category }}</el-tag>
              <el-tag size="small" type="success" style="margin-left:6px">{{ item.type }}</el-tag>
            </div>
            <div style="color:#409eff;font-size:13px">💡 {{ item.reason }}</div>
          </el-card>
          <el-card v-if="!s.recList.length && !s.recLoading" shadow="hover">
            <el-empty description="暂无个性化推荐——去资源检索页浏览、收藏、评分，推荐会越来越准"
                      :image-size="80"></el-empty>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card header="🔥 热门资源（冷启动兜底）">
            <div v-for="h in s.hotList" :key="h.resource_id" style="padding:6px 0;border-bottom:1px dashed #eee;cursor:pointer"
                 @click="openDetail(h)">
              <b style="font-size:13px">{{ h.title }}</b>
              <div style="color:#999;font-size:12px">热度 {{ h.hot }}</div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>`
  };
})();
