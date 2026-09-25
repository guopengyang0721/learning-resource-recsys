/** 管理后台外壳（管理员）：内部子导航 —— 数据看板 / 资源管理 / 用户管理 */
(function () {
  const C = window.App.components = window.App.components || {};

  C.AdminView = {
    setup() {
      const { ref } = window.Vue;
      const { ElMessage } = window.ElementPlus;
      const section = ref('dashboard');   // dashboard | resources | users
      const bcVisible = ref(false);
      const bcForm = ref({ title: '', content: '' });
      const publishing = ref(false);      // 发布中防重复提交
      const A = window.App.api;

      async function publish() {
        if (publishing.value) return;
        const title = bcForm.value.title.trim();
        if (title.length < 2) return ElMessage.warning('公告标题至少 2 个字符');
        if (!bcForm.value.content.trim()) return ElMessage.warning('公告内容不能为空');
        publishing.value = true;
        try {
          const r = await A.broadcast(bcForm.value);
          if (r.detail) return ElMessage.error(r.detail);
          ElMessage.success(r.message);
          bcVisible.value = false;
          bcForm.value = { title: '', content: '' };
        } catch (e) {
          ElMessage.error('公告发布失败，请稍后重试');
        } finally { publishing.value = false; }
      }

      /** 导出 CSV（带令牌请求，浏览器直接下载） */
      async function exportCsv(kind, filename) {
        try {
          await A.exportCsv(kind, filename);
          ElMessage.success(`${filename} 已开始下载`);
        } catch (e) {
          ElMessage.error(e.message || '导出失败');
        }
      }

      const retraining = ref(false);
      /** 手动触发推荐模型全量重训练（管理员专用接口） */
      async function retrain() {
        if (retraining.value) return;
        retraining.value = true;
        try {
          const r = await A.retrainModel();
          if (r.detail) return ElMessage.error(r.detail);
          ElMessage.success(r.message);
        } catch (e) {
          ElMessage.error('重训练失败，请稍后重试');
        } finally { retraining.value = false; }
      }

      return { section, bcVisible, bcForm, publish, exportCsv, retrain, retraining };
    },
    template: `
    <div>
      <el-card shadow="never" :body-style="{padding:'10px 16px'}">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <el-radio-group v-model="section">
            <el-radio-button value="dashboard">📊 数据看板</el-radio-button>
            <el-radio-button value="resources">📚 资源管理</el-radio-button>
            <el-radio-button value="users">👥 用户管理</el-radio-button>
          </el-radio-group>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            <el-dropdown v-if="section === 'dashboard'" @command="k => exportCsv(k, k + '.csv')">
              <el-button type="success" plain>📤 导出数据</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="users">👥 用户数据 CSV</el-dropdown-item>
                  <el-dropdown-item command="resources">📚 资源数据 CSV</el-dropdown-item>
                  <el-dropdown-item command="behaviors">📈 行为日志 CSV</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-if="section === 'dashboard'" plain :loading="retraining"
                       @click="retrain">🔄 重新训练模型</el-button>
            <el-button type="warning" plain @click="bcVisible = true">📢 发布系统公告</el-button>
          </div>
        </div>
      </el-card>

      <el-dialog v-model="bcVisible" title="📢 发布系统公告" width="480px">
        <div style="color:#666;font-size:13px;margin-bottom:10px">公告将推送给全部用户的消息通知中心。</div>
        <el-form label-width="60px">
          <el-form-item label="标题">
            <el-input v-model="bcForm.title" maxlength="100" placeholder="公告标题"></el-input>
          </el-form-item>
          <el-form-item label="内容">
            <el-input v-model="bcForm.content" type="textarea" :rows="4" maxlength="500"
                      placeholder="公告内容（500 字以内）"></el-input>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="bcVisible = false">取消</el-button>
          <el-button type="primary" :loading="publishing" @click="publish">发 布</el-button>
        </template>
      </el-dialog>

      <div v-if="section === 'dashboard'"><stats-view></stats-view></div>
      <div v-else-if="section === 'resources'"><resource-admin-view></resource-admin-view></div>
      <div v-else><user-admin-view></user-admin-view></div>
    </div>`
  };
})();
