/** 资源检索视图：关键词 / 分类筛选、列表、评分 / 收藏 / 浏览行为上报 */
(function () {
  const C = window.App.components = window.App.components || {};
  const TYPE_NAME = { video: '视频', doc: '文档', ppt: '课件', question: '题库', book: '书籍', course: '系列课' };

  C.ResourcesView = {
    setup() {
      const { state, search, rate, fav, openDetail } = window.App.store;
      return { s: state, search, rate, fav, openDetail, typeName: t => TYPE_NAME[t] || t };
    },
    mounted() { this.search(); },   // 首次激活（含 URL 直达 /search）自动加载
    template: `
    <div>
      <el-card shadow="never" :body-style="{padding:'12px 16px'}" style="margin-bottom:12px">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <el-input v-model="s.keyword" placeholder="关键词检索" style="width:200px" clearable
                    @keyup.enter="s.page=1;search()"></el-input>
          <el-select v-model="s.category" placeholder="全部分类" style="width:140px" clearable>
            <el-option v-for="c in s.categories" :key="c" :label="c" :value="c"></el-option>
          </el-select>
          <el-button type="primary" @click="s.page=1;search()">检 索</el-button>
        </div>
        <el-divider style="margin:12px 0"></el-divider>
        <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:13px;color:#666">类型：</span>
            <el-checkbox-group v-model="s.types" @change="s.page=1;search()">
              <el-checkbox v-for="t in s.typeOptions" :key="t.key" :value="t.key"
                           style="margin-right:10px">{{ t.name }}</el-checkbox>
            </el-checkbox-group>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:13px;color:#666">上传时间：</span>
            <el-select v-model="s.days" style="width:120px" @change="s.page=1;search()">
              <el-option label="全部时间" :value="0"></el-option>
              <el-option label="最近一周" :value="7"></el-option>
              <el-option label="最近一月" :value="30"></el-option>
              <el-option label="最近一学期" :value="180"></el-option>
            </el-select>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:13px;color:#666">排序：</span>
            <el-select v-model="s.sort" style="width:140px" @change="s.page=1;search()">
              <el-option label="🔥 热度最高" value="hot"></el-option>
              <el-option label="⭐ 评分最高" value="rating"></el-option>
              <el-option label="🆕 最新上传" value="new"></el-option>
              <el-option label="📈 难度从低到高" value="difficulty"></el-option>
            </el-select>
          </div>
        </div>
      </el-card>
      <el-table :data="s.resList" border @row-click="openDetail" style="cursor:pointer"
                v-loading="s.resLoading">
        <el-table-column prop="title" label="资源标题" min-width="220"></el-table-column>
        <el-table-column prop="category" label="分类" width="110"></el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="scope">{{ typeName(scope.row.type) }}</template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="70"></el-table-column>
        <el-table-column prop="click_count" label="热度" width="80"></el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-rate v-model="scope.row._r" size="small" @change="v=>rate(scope.row,v)"
                     @click.stop></el-rate>
            <el-button size="small" :text="!scope.row.favorited" :type="scope.row.favorited ? 'success' : 'primary'"
                       :plain="!scope.row.favorited"
                       @click.stop="fav(scope.row)">{{ scope.row.favorited ? '★ 已收藏' : '☆ 收藏' }}</el-button>
            <el-button size="small" text @click.stop="openDetail(scope.row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination style="margin-top:12px" layout="total, prev, pager, next, jumper" :total="s.resTotal"
                     :page-size="8" v-model:current-page="s.page" @current-change="search"></el-pagination>
    </div>`
  };
})();
