/** 应用入口：侧边导航布局装配 + History 路由 + 自动登录参数 */
(function () {
  const { createApp, computed } = window.Vue;
  const store = window.App.store;

  const PAGE_META = {
    recommend: ['个性化推荐', '基于你的行为与兴趣标签，为你精选学习资源'],
    resources: ['资源检索', '多条件组合筛选，快速定位目标学习资源'],
    profile: ['个人中心', '管理个人资料、兴趣标签与行为足迹'],
    teacher: ['教师工作台', '上传与管理你自己的教学资源'],
    admin: ['管理后台', '数据看板、资源审核与用户管理'],
  };

  const app = createApp({
    setup() {
      const qs = new URLSearchParams(location.search);

      // ---- History 路由：/login 登录页；主界面五个页签各对应真实路径 ----
      const PATH_TAB = { '/': 'recommend', '/recommend': 'recommend', '/search': 'resources',
                         '/profile': 'profile', '/teacher': 'teacher', '/admin': 'admin' };
      const TAB_PATH = { recommend: '/recommend', resources: '/search', profile: '/profile',
                         teacher: '/teacher', admin: '/admin' };

      function syncRoute() {
        let p = location.pathname.replace(/\/+$/, '') || '/';
        if (p === '/login') { store.state.route = 'login'; return; }
        store.state.route = 'main';
        let tab = PATH_TAB[p] || 'recommend';
        // 角色守卫：教师/管理员页不对低权限角色开放
        if (tab === 'teacher' && !['teacher', 'admin'].includes(store.state.me.role)) tab = 'recommend';
        if (tab === 'admin' && store.state.me.role !== 'admin') tab = 'recommend';
        if (p !== '/' && PATH_TAB[p] && p !== TAB_PATH[tab]) {
          history.replaceState({}, '', TAB_PATH[tab]);   // 角色守卫归位时同步修正地址栏
        }
        store.state.activeTab = tab;
      }
      window.App.navigate = function (path) {
        if (location.pathname !== path) history.pushState({}, '', path);
        syncRoute();
      };
      window.addEventListener('popstate', syncRoute);
      syncRoute();

      // 未登录访问主界面 → 归位到 /login（replaceState 不留历史记录）
      if (store.state.route === 'main' && !store.state.me.user_id) {
        history.replaceState({}, '', '/login');
        store.state.route = 'login';
      }

      // 自动化测试入口（仅本机生效）：本地无头浏览器巡检脚本用 ?autologin=1&user=xxx 免去重复填表，
      // 账号与种子数据中的演示账号一致。部署到其他主机后该参数自动失效，不构成登录通道。
      const isLocal = ['127.0.0.1', 'localhost', '::1'].includes(location.hostname);
      const demoUsers = { student: ['student001', '123456'], teacher: ['teacher01', '123456'],
                          admin: ['admin', 'admin123'] };
      const demo = isLocal && qs.get('autologin') === '1' ? demoUsers[qs.get('user') || 'student'] : null;
      if (demo) { store.state.loginForm.username = demo[0]; store.state.loginForm.password = demo[1]; }

      const afterLogin = () => {
        const tab = qs.get('tab');
        const PATHS = { recommend: '/recommend', resources: '/search', profile: '/profile',
                        teacher: '/teacher', admin: '/admin' };
        // 经 navigate → syncRoute，角色守卫会拦截学生/教师访问受限页签
        if (tab && PATHS[tab]) window.App.navigate(PATHS[tab]);
      };

      if (store.state.me.user_id) {
        // 启动时向后端校验本地登录态，失效则清除并回到登录页（防绕过）
        window.App.api.verify().then(() => {
          // 校验通过后按角色重新同步路径（防止低权限角色停留在受限路径上）
          syncRoute();
          store.loadRec(); store.loadHot(); store.loadNotifications(); afterLogin();
        }).catch(() => {});
      } else if (isLocal && qs.get('autologin') === '1') {
        store.doLogin().then(afterLogin);
      } else {
        store.loadHot();
      }

      const meta = computed(() => PAGE_META[store.state.activeTab] || PAGE_META.recommend);
      return { s: store.state, meta, onTab: store.onTab, doLogout: store.doLogout,
               openDetail: store.openDetail,
               loadNotifications: store.loadNotifications,
               markNotifRead: store.markNotifRead,
               readAllNotifications: store.readAllNotifications };
    },
    template: `
    <div>
      <login-view v-if="s.route === 'login' || !s.me.user_id"></login-view>
      <div v-else class="main-layout">
        <aside class="side-nav">
          <div class="nav-logo">
            <span class="logo-ic">📚</span>
            <div>
              <div class="t1">学习资源推荐系统</div>
              <div class="t2">Web 数据挖掘课程原型</div>
            </div>
            <el-popover placement="bottom-end" :width="330" trigger="click" popper-class="notif-pop">
              <template #reference>
                <el-badge :value="s.notif.unread" :hidden="!s.notif.unread" :max="99"
                          style="margin-left:auto;cursor:pointer">
                  <span style="font-size:20px;cursor:pointer"
                        @click="loadNotifications()">🔔</span>
                </el-badge>
              </template>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <b>消息通知</b>
                <el-link type="primary" :underline="false" style="font-size:12px"
                         @click="readAllNotifications">全部已读</el-link>
              </div>
              <div style="max-height:320px;overflow:auto">
                <div v-for="n in s.notif.items" :key="n.id"
                     style="padding:8px 6px;border-bottom:1px dashed #eee;cursor:pointer"
                     @click="markNotifRead(n.id)">
                  <div style="display:flex;justify-content:space-between;gap:6px">
                    <b style="font-size:13px" :style="{color: n.is_read ? '#888' : '#243b6b'}">{{ n.title }}</b>
                    <el-badge v-if="!n.is_read" is-dot></el-badge>
                  </div>
                  <div style="color:#666;font-size:12px;margin-top:2px">{{ n.content }}</div>
                  <div style="color:#bbb;font-size:11px;margin-top:2px">{{ n.time }}</div>
                </div>
                <div v-if="!s.notif.items.length" style="color:#999;font-size:13px;text-align:center;padding:16px 0">
                  暂无消息
                </div>
              </div>
            </el-popover>
          </div>
          <el-menu :default-active="s.activeTab" class="nav-menu" @select="onTab">
            <el-menu-item index="recommend"><span class="ic">🎯</span>个性化推荐</el-menu-item>
            <el-menu-item index="resources"><span class="ic">🔍</span>资源检索</el-menu-item>
            <el-menu-item index="profile"><span class="ic">👤</span>个人中心</el-menu-item>
            <el-menu-item v-if="s.me.role === 'teacher' || s.me.role === 'admin'"
                          index="teacher"><span class="ic">🧑‍🏫</span>教师工作台</el-menu-item>
            <el-menu-item v-if="s.me.role === 'admin'" index="admin"><span class="ic">🛡️</span>管理后台</el-menu-item>
          </el-menu>
          <div class="nav-user">
            <div class="nav-avatar">🎓</div>
            <div class="nav-uinfo">
              <div class="un">{{ s.me.nickname }}</div>
              <div class="ur">{{ s.me.role }} · {{ s.me.gender || '保密' }}</div>
            </div>
            <el-button size="small" text style="color:#c9d6f0" @click="doLogout">退出</el-button>
          </div>
        </aside>
        <main class="main-content">
          <div class="page-head">
            <h2>{{ meta[0] }}</h2>
            <p>{{ meta[1] }}</p>
          </div>
          <recommend-view v-if="s.activeTab === 'recommend'"></recommend-view>
          <resources-view v-else-if="s.activeTab === 'resources'"></resources-view>
          <profile-view v-else-if="s.activeTab === 'profile'"></profile-view>
          <teacher-view v-else-if="s.activeTab === 'teacher'"></teacher-view>
          <admin-view v-else-if="s.activeTab === 'admin'"></admin-view>
        </main>
      </div>
      <detail-dialog></detail-dialog>
    </div>`
  });

  const C = window.App.components;
  app.component('login-view', C.LoginView);
  app.component('recommend-view', C.RecommendView);
  app.component('resources-view', C.ResourcesView);
  app.component('profile-view', C.ProfileView);
  app.component('teacher-view', C.TeacherView);
  app.component('admin-view', C.AdminView);
  app.component('stats-view', C.StatsView);
  app.component('resource-admin-view', C.ResourceAdminView);
  app.component('user-admin-view', C.UserAdminView);
  app.component('detail-dialog', C.DetailDialog);
  // 中文语言包（分页"前往 X 页"、表格"暂无数据"等组件内置文案）；缺失时退回默认
  app.use(window.ElementPlus, window.ElementPlusLocaleZhCn ? { locale: window.ElementPlusLocaleZhCn } : {});
  app.mount('#app');
})();
