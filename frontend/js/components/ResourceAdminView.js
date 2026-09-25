/** 资源审核与管理（管理员）：状态筛选 + 上架/下架/删除 */
(function () {
  const { ref } = window.Vue;
  const { ElMessage, ElMessageBox } = window.ElementPlus;
  const C = window.App.components = window.App.components || {};
  const A = window.App.api;

  C.ResourceAdminView = {
    setup() {
      const items = ref([]); const total = ref(0);
      const page = ref(1); const size = 10;
      const status = ref(''); const keyword = ref('');
      const statusName = { pending: '待审核', online: '已上架', offline: '已下架' };
      const statusType = { pending: 'warning', online: 'success', offline: 'info' };

      async function load() {
        try {
          const r = await A.adminResources({ keyword: keyword.value, status: status.value, page: page.value, size });
          items.value = r.items || []; total.value = r.total || 0;
        } catch (e) { ElMessage.error('资源列表加载失败，请稍后重试'); }
      }
      /** 审核操作：下架/驳回属负向操作需二次确认，操作期间防连点 */
      function setStatus(row, st) {
        const doIt = async () => {
          row._busy = true;
          try {
            const r = await A.setResourceStatus(row.id, st);
            if (r.detail) return ElMessage.error(r.detail);
            ElMessage.success(r.message || '操作成功'); load();
          } catch (e) { ElMessage.error('操作失败，请稍后重试'); }
          finally { row._busy = false; }
        };
        if (st === 'offline') {
          ElMessageBox.confirm(`确定下架《${row.title}》？学生端将不再展示该资源。`, '确认下架', { type: 'warning' })
            .then(doIt).catch(() => {});
        } else {
          doIt();
        }
      }
      function del(row) {
        ElMessageBox.confirm(`确定删除《${row.title}》？其评分/收藏/行为记录将一并删除，不可恢复。`, '危险操作', { type: 'warning' })
          .then(async () => {
            try {
              const r = await A.deleteResource(row.id);
              if (r.detail) return ElMessage.error(r.detail);
              ElMessage.success(r.message);
              const maxPage = Math.max(1, Math.ceil((total.value - 1) / size));
              if (page.value > maxPage) page.value = maxPage;
              load();
            } catch (e) { ElMessage.error('删除失败，请稍后重试'); }
          })
          .catch(() => {});
      }

      return { items, total, page, size, status, keyword, statusName, statusType, load, setStatus, del };
    },
    mounted() { this.load(); },
    template: `
    <div>
      <el-card shadow="never" :body-style="{padding:'10px 16px'}">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <el-radio-group v-model="status" @change="page=1;load()">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="pending">待审核</el-radio-button>
            <el-radio-button value="online">已上架</el-radio-button>
            <el-radio-button value="offline">已下架</el-radio-button>
          </el-radio-group>
          <el-input v-model="keyword" placeholder="按标题搜索" style="width:220px" clearable @keyup.enter="page=1;load()"></el-input>
          <el-button type="primary" @click="page=1;load()">查询</el-button>
          <span style="color:#98a5bd;font-size:13px;margin-left:auto">共 {{ total }} 条</span>
        </div>
      </el-card>

      <el-card style="margin-top:12px">
        <el-table :data="items" size="small">
          <el-table-column prop="id" label="ID" width="60"></el-table-column>
          <el-table-column prop="title" label="资源标题" min-width="220"></el-table-column>
          <el-table-column prop="uploader" label="上传者" width="110"></el-table-column>
          <el-table-column prop="category" label="分类" width="100"></el-table-column>
          <el-table-column prop="click_count" label="热度" width="70"></el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="scope">
              <el-tag size="small" :type="statusType[scope.row.status]">{{ statusName[scope.row.status] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220">
            <template #default="scope">
              <el-button v-if="scope.row.status !== 'online'" size="small" type="success" plain
                         @click="setStatus(scope.row, 'online')">上 架</el-button>
              <el-button v-if="scope.row.status === 'online'" size="small" type="warning" plain
                         @click="setStatus(scope.row, 'offline')">下 架</el-button>
              <el-button v-if="scope.row.status === 'pending'" size="small" plain
                         @click="setStatus(scope.row, 'offline')">驳 回</el-button>
              <el-button size="small" type="danger" plain @click="del(scope.row)">删 除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:12px" layout="total, prev, pager, next, jumper" :total="total"
                       :page-size="size" v-model:current-page="page" @current-change="load"></el-pagination>
      </el-card>
    </div>`
  };
})();
