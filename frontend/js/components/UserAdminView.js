/** 用户管理（管理员）：列表 / 教师邀请码 / 禁用启用 / 重置密码 */
(function () {
    const { ref } = window.Vue;
    const { ElMessage, ElMessageBox } = window.ElementPlus;
    /** 角色中文名（显示用；权限判断仍用英文 role） */
    const ROLE_NAME = window.App.store.ROLE_NAME || {};
    const roleName = (r) => ROLE_NAME[r] || r;
  const C = window.App.components = window.App.components || {};
  const A = window.App.api;

  C.UserAdminView = {
    setup() {
      const items = ref([]); const total = ref(0);
      const page = ref(1); const size = 10; const keyword = ref('');
      const inviteVisible = ref(false);
      const inviteItems = ref([]);
      const latestCode = ref('');

      async function load() {
        try {
          const r = await A.adminUsers({ keyword: keyword.value, page: page.value, size });
          items.value = r.items || []; total.value = r.total || 0;
        } catch (e) { ElMessage.error('用户列表加载失败，请稍后重试'); }
      }
      async function toggle(row) {
        const target = row.status === 'active' ? 'disabled' : 'active';
        const tip = target === 'disabled'
          ? `确定禁用账号 ${row.username}？禁用后该用户将无法登录。`
          : `确定启用账号 ${row.username}？`;
        ElMessageBox.confirm(tip, '确认操作', { type: 'warning' })
          .then(async () => {
            try {
              const r = await A.setUserStatus(row.id, target);
              if (r.detail) return ElMessage.error(r.detail);
              ElMessage.success(r.message); load();
            } catch (e) { ElMessage.error('操作失败，请稍后重试'); }
          })
          .catch(() => {});
      }
      /** 重置密码时的默认值：与后端 config.DEFAULT_RESET_PASSWORD 保持一致 */
      const DEFAULT_RESET_PWD = '123456';

      function openReset(row) {
        ElMessageBox.prompt(
          `为账号 ${row.username} 设置新密码（6~64 位）。已预填默认密码 ${DEFAULT_RESET_PWD}，`
          + '直接确认即可；也可改成其他密码。',
          '重置密码',
          { inputValue: DEFAULT_RESET_PWD, inputPattern: /^.{6,64}$/, inputErrorMessage: '密码需为 6~64 位' })
          .then(async ({ value }) => {
            try {
              const r = await A.resetUserPassword(row.id, value);
              if (r.detail) return ElMessage.error(r.detail);
              ElMessage.success(r.message);      // 后端会回显生效的密码，便于转告用户
            } catch (e) { ElMessage.error('重置失败，请稍后重试'); }
          })
          .catch(() => {});
      }
      /** 删除账号：二次确认 + 提示将级联清除其行为数据（不可恢复） */
      function del(row) {
        ElMessageBox.confirm(
          `确定删除账号「${row.username}」？其评分、收藏、行为记录与通知将一并删除，且不可恢复。`
          + (row.role === 'teacher' ? '其上传的资源将保留，但不再署名。' : ''),
          '⚠️ 危险操作', { type: 'error', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' })
          .then(async () => {
            try {
              const r = await A.deleteUser(row.id);
              if (r.detail) return ElMessage.error(r.detail);
              ElMessage.success(r.message);
              const maxPage = Math.max(1, Math.ceil((total.value - 1) / size));
              if (page.value > maxPage) page.value = maxPage;
              load();
            } catch (e) { ElMessage.error('删除失败，请稍后重试'); }
          })
          .catch(() => {});
      }

      /** 教师邀请码：生成一次性码 + 查看使用状态 */
      async function openInvites() {
        inviteVisible.value = true;
        latestCode.value = '';
        await loadInvites();
      }
      async function loadInvites() {
        try {
          const r = await A.inviteCodes();
          inviteItems.value = r.items || [];
        } catch (e) { ElMessage.error('邀请码列表加载失败'); }
      }
      const genLoading = ref(false);
      async function genCode() {
        if (genLoading.value) return;         // 防连点：一次生成两个一次性码
        genLoading.value = true;
        try {
          const r = await A.generateInviteCode();
          if (r.detail) return ElMessage.error(r.detail);
          latestCode.value = r.code;
          ElMessage.success(r.message);
          loadInvites();
        } catch (e) { ElMessage.error('生成失败，请稍后重试'); }
        finally { genLoading.value = false; }
      }

      return { items, total, page, size, keyword, load, toggle, openReset, del, roleName,
               inviteVisible, inviteItems, latestCode, openInvites, genCode, genLoading };
    },
    mounted() { this.load(); },
    template: `
    <div>
      <el-card shadow="never" :body-style="{padding:'10px 16px'}">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <el-input v-model="keyword" placeholder="按用户名/昵称搜索" style="width:220px" clearable @keyup.enter="page=1;load()"></el-input>
          <el-button type="primary" @click="page=1;load()">查询</el-button>
          <el-button type="warning" plain @click="openInvites">🎟️ 教师邀请码</el-button>
          <span style="color:#98a5bd;font-size:13px;margin-left:auto">共 {{ total }} 个账号</span>
        </div>
      </el-card>

      <el-card style="margin-top:12px">
        <el-table :data="items" size="small">
          <el-table-column prop="id" label="ID" width="60"></el-table-column>
          <el-table-column prop="username" label="用户名" width="120"></el-table-column>
          <el-table-column prop="nickname" label="昵称" width="120"></el-table-column>
          <el-table-column prop="role" label="角色" width="90">
            <template #default="scope">
              <el-tag size="small" :type="scope.row.role==='admin' ? 'danger' : (scope.row.role==='teacher' ? 'warning' : 'info')">
                {{ roleName(scope.row.role) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="行为数据" min-width="160">
            <template #default="scope">
              <span style="font-size:12px;color:#666">评分 {{ scope.row.scores }} · 收藏 {{ scope.row.favorites }} · 日志 {{ scope.row.logs }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="80">
            <template #default="scope">
              <el-tag size="small" :type="scope.row.status==='active' ? 'success' : 'danger'">
                {{ scope.row.status==='active' ? '正常' : '已禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="270">
            <template #default="scope">
              <el-button v-if="scope.row.status==='active'" size="small" type="danger" plain
                         :disabled="scope.row.role==='admin'" @click="toggle(scope.row)">禁 用</el-button>
              <el-button v-else size="small" type="success" plain @click="toggle(scope.row)">启 用</el-button>
              <el-button size="small" plain @click="openReset(scope.row)">重置密码</el-button>
              <el-button size="small" type="danger" :disabled="scope.row.role==='admin'"
                         @click="del(scope.row)">删 除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:12px" layout="total, prev, pager, next, jumper" :total="total"
                       :page-size="size" v-model:current-page="page" @current-change="load"></el-pagination>
      </el-card>

      <!-- 教师邀请码弹窗 -->
      <el-dialog v-model="inviteVisible" title="🎟️ 教师注册邀请码" width="520px">
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
          <el-button type="primary" :loading="genLoading" @click="genCode">生成新邀请码</el-button>
          <span v-if="latestCode" style="font-size:15px">
            最新码：<b style="color:#409eff;letter-spacing:2px">{{ latestCode }}</b>
            <span style="color:#98a5bd;font-size:12px;margin-left:6px">（发给教师，注册时填入）</span>
          </span>
        </div>
        <el-table :data="inviteItems" size="small" max-height="320">
          <el-table-column prop="code" label="邀请码" width="130">
            <template #default="scope">
              <b style="letter-spacing:1px">{{ scope.row.code }}</b>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="生成时间" width="130"></el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="scope">
              <el-tag size="small" :type="scope.row.used ? 'info' : 'success'">
                {{ scope.row.used ? '已使用' : '未使用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="使用者" min-width="120">
            <template #default="scope">{{ scope.row.used_by || '—' }}</template>
          </el-table-column>
        </el-table>
        <div style="color:#98a5bd;font-size:12px;margin-top:8px">
          每个邀请码只能使用一次；教师注册时选择「教师」身份并填入即可获得教师权限。
        </div>
      </el-dialog>
    </div>`
  };
})();
