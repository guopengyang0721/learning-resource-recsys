/** 全局状态与业务动作：组件只读 state、调用动作，单一数据源 */
(function () {
  const { reactive } = window.Vue;
  const { ElMessage, ElMessageBox } = window.ElementPlus;
  const A = window.App.api;

  /** 角色中文名：仅用于界面显示；权限判断一律继续用英文 role */
  const ROLE_NAME = { student: '学生', teacher: '教师', admin: '管理员' };
  const FAV_PAGE_SIZE = 12;                    // 我的收藏每页条数（3 列 × 4 行），分页组件与此保持一致

  const state = reactive({
    me: (function () {
      const me = window.App.readMe ? window.App.readMe() :
        JSON.parse(localStorage.getItem('me') || sessionStorage.getItem('me') || 'null');
      return me || { nickname: '游客', user_id: 0, role: 'student' };
    })(),
    loginForm: { username: '', password: '', remember: false },
    regForm: { username: '', password: '', nickname: '', interests: [], gender: '保密', grade: '', college: '', sec_question: '', sec_answer: '', role: 'student', invite_code: '' },
    loginLoading: false,
    route: 'main',              // 'login' | 'main'（由 app.js 的路由同步函数维护）
    activeTab: 'recommend',

    algo: 'user_cf',
    recList: [], recSource: '', recLoading: false,
    hotList: [],

    keyword: '', category: '',
    categories: ['软件工程', '机器学习', '数据库', '计算机网络', '算法', 'Web开发', '人工智能'],
    types: [], typeOptions: [
        { key: 'video', name: '视频' }, { key: 'doc', name: '文档' },
        { key: 'ppt', name: '课件' }, { key: 'question', name: '题库' },
        { key: 'book', name: '书籍' }, { key: 'course', name: '系列课' }],
    sort: 'hot', days: 0,
    resList: [], resTotal: 0, page: 1, resLoading: false,

    stats: null,

    detail: { visible: false, loading: false, info: null, similar: [] },
    history: { items: [], loading: false },
    favs: { items: [], total: 0, page: 1, sort: 'time', loading: false },
    notif: { items: [], unread: 0, open: false },
    portrait: { distribution: {}, total: 0 },
  });

  function persistLogin(r) {
    // 保留既有 remember 标志（如升级教师等接口响应不含该字段时，不能把 7 天免登录降级为会话级）
    const saved = window.App.readMe ? window.App.readMe() : null;
    const payload = Object.assign({}, r, { remember: r.remember !== undefined ? r.remember : !!(saved && saved.remember) });
    Object.assign(state.me, payload);
    window.App.saveMe(payload);    // 按 remember 标志决定存 localStorage 还是 sessionStorage
    state.me.token = payload.token;
  }

  async function doLogin() {
    if (state.loginLoading) return;
    state.loginLoading = true;
    try {
      const r = await A.login(state.loginForm);
      if (!r.token) { ElMessage.error(r.detail || '登录失败'); return; }
      persistLogin(r);
      ElMessage.success('登录成功，欢迎 ' + r.nickname +
        (r.remember ? '（7 天内免登录）' : '（2 小时后需重新登录）'));
      if (window.App.navigate) window.App.navigate('/'); else state.route = 'main';
      loadRec(); loadHot();
    } catch (e) {
      ElMessage.error('网络异常，请检查连接后重试');
    } finally { state.loginLoading = false; }
  }

  /** 注册并自动登录（带兴趣标签，供冷启动推荐） */
  async function doRegister() {
    if (state.loginLoading) return;
    state.loginLoading = true;
    try {
      const r = await A.register(state.regForm);
      if (!r.token) { ElMessage.error(r.detail || '注册失败'); return; }
      persistLogin(r);
      ElMessage.success(`注册成功，欢迎 ${r.nickname}！已根据你的兴趣生成推荐`);
      if (window.App.navigate) window.App.navigate('/'); else state.route = 'main';
      loadRec(); loadHot();
    } catch (e) {
      ElMessage.error('网络异常，请检查连接后重试');
    } finally { state.loginLoading = false; }
  }

  /** 更新兴趣类别并触发推荐重训练 */
  async function saveInterests(interests) {
    try {
      const r = await A.updateInterests(interests);
      state.me.interests = r.interests;
      window.App.saveMe(state.me);
      ElMessage.success(r.message);
      loadRec();
      return true;
    } catch (e) { ElMessage.error('兴趣保存失败，请稍后重试'); return false; }
  }

  /** 修改个人资料（昵称 / 性别 / 年级 / 学院） */
  async function updateProfile(data) {
    let r;
    try {
      r = await A.updateProfile(data);
    } catch (e) {
      ElMessage.error('保存失败，请检查网络后重试');
      return { detail: '网络异常' };
    }
    if (r.detail) { ElMessage.error(r.detail); return r; }   // 服务端校验失败
    Object.assign(state.me, { nickname: r.nickname, gender: r.gender,
                              grade: r.grade, college: r.college });
    window.App.saveMe(state.me);
    ElMessage.success(r.message);
    return r;
  }

  function doLogout() {
    sessionStorage.removeItem('me');
    localStorage.removeItem('me');
    Object.assign(state.me, { nickname: '游客', user_id: 0, role: 'student', token: '' });
    // 清空上一账号的列表缓存与筛选条件，避免换账号登录后短暂看到他人数据
    state.recList = []; state.recSource = ''; state.hotList = [];
    state.algo = 'user_cf'; state.keyword = ''; state.category = ''; state.types = [];
    state.sort = 'hot'; state.days = 0;
    state.resList = []; state.resTotal = 0; state.page = 1;
    state.favs = { items: [], total: 0, page: 1, sort: 'time', loading: false };
    state.history = { items: [], loading: false };
    state.notif = { items: [], unread: 0, open: false };
    state.stats = null; state.portrait = { distribution: {}, total: 0 };
    state.detail = { visible: false, loading: false, info: null, similar: [] };
    if (window.App.navigate) window.App.navigate('/login'); else state.route = 'login';
  }

  // 请求竞态保护：快速切换算法/页签时只接受最新一次响应，避免旧数据覆盖新数据
  let recSeq = 0, searchSeq = 0, detailSeq = 0;

  async function loadRec() {
    if (!state.me.user_id) return;
    state.recLoading = true;
    const seq = ++recSeq;
    try {
      const r = await A.recommend(state.me.user_id, { algo: state.algo });
      if (seq !== recSeq) return;                 // 已有更新的请求发出，丢弃本次结果
      state.recList = r.items || [];
      state.recSource = r.source || '';
    } catch (e) {
      if (seq === recSeq) ElMessage.error('推荐加载失败，请点击「刷新推荐」重试');
    } finally {
      if (seq === recSeq) state.recLoading = false;
    }
  }

  async function loadHot() {
    try {
      const r = await A.hotList(5);
      state.hotList = r.items || [];
    } catch (e) { /* 热门栏失败不影响主流程，静默 */ }
  }

  async function search() {
    state.resLoading = true;
    const seq = ++searchSeq;
    try {
      const r = await A.searchResources({
        keyword: state.keyword, category: state.category, page: state.page, size: 8,
        type: (state.types || []).join(','), sort: state.sort, days: state.days,
      });
      if (seq !== searchSeq) return;
      state.resList = r.items || [];
      state.resTotal = r.total || 0;
    } catch (e) {
      if (seq === searchSeq) ElMessage.error('资源检索失败，请稍后重试');
    } finally {
      if (seq === searchSeq) state.resLoading = false;
    }
  }

  async function rate(row, val) {
    const id = row.id ?? row.resource_id;
    try {
      await A.reportBehavior({ resource_id: id, action: 'rate', value: val });
      ElMessage.success(`已为《${row.title}》评分 ${val} 星，行为将用于下次推荐`);
    } catch (e) { ElMessage.error('评分上报失败，请稍后重试'); }
  }

  /** 收藏 / 取消收藏（按当前状态切换），并同步收藏列表 */
  async function fav(row) {
    const id = row.id ?? row.resource_id;
    if (row._favBusy) return;                     // 防连点导致的重复请求
    row._favBusy = true;
    try {
      let r;
      if (row.favorited) {
        r = await A.removeFavorite(id);
        if (r.detail) { ElMessage.error(r.detail); return; }   // 服务端拒绝时不翻转状态
        row.favorited = false;
      } else {
        r = await A.addFavorite(id);
        if (r.detail) { ElMessage.error(r.detail); return; }
        row.favorited = true;
      }
      ElMessage.success(r.message || '操作成功');
      loadFavorites();
    } catch (e) {
      ElMessage.error('收藏操作失败，请稍后重试');
    } finally { row._favBusy = false; }
  }

  async function view(row, silent = false) {
    // 推荐 / 热门 / 相似推荐返回的条目只有 resource_id，没有 id
    const id = row.id ?? row.resource_id;
    if (!id) return;
    try {
      await A.reportBehavior({ resource_id: id, action: 'view' });
      if (!silent) ElMessage.info('已记录浏览行为：' + row.title);
    } catch (e) { /* 行为上报失败不打扰用户（401 已由 api 层处理） */ }
  }

  /** 资源详情弹窗：详情 + "看了又看"相似推荐（Item-CF），并静默记录浏览行为 */
  async function openDetail(row) {
    const id = row.id ?? row.resource_id;
    if (!id) return;
    state.detail = { visible: true, loading: true, info: null, similar: [] };
    view(row, true);
    const seq = ++detailSeq;                      // 连续点开不同资源时，只保留最后一次
    try {
      const [info, sim] = await Promise.all([A.resourceDetail(id), A.similarResources(id)]);
      if (seq !== detailSeq) return;
      state.detail.info = info;
      state.detail.similar = sim.items || [];
    } catch (e) {
      if (seq === detailSeq) {
        state.detail.info = null;
        state.detail.visible = false;   // 失败时关闭弹窗，避免滞留全空白弹窗
        ElMessage.error('详情加载失败，请稍后重试');
      }
    } finally {
      if (seq === detailSeq) state.detail.loading = false;
    }
  }

  async function loadHistory() {
    state.history.loading = true;
    try {
      const r = await A.myHistory();
      state.history.items = r.items || [];
    } catch (e) { ElMessage.error('加载足迹失败，请稍后重试'); }
    finally { state.history.loading = false; }
  }
  async function removeHistory(logId) {
    try {
      await A.removeHistory(logId);
      ElMessage.success('记录已删除');
      loadHistory();
    } catch (e) { ElMessage.error('删除失败，请稍后重试'); }
  }
  async function loadFavorites(p) {
    state.favs.loading = true;
    try {
      if (typeof p === 'number') state.favs.page = p;
      const r = await A.myFavorites(state.favs.page || 1, FAV_PAGE_SIZE, state.favs.sort);
      state.favs.items = r.items || [];
      state.favs.total = r.total || 0;
    } catch (e) { ElMessage.error('加载收藏失败，请稍后重试'); }
    finally { state.favs.loading = false; }
  }

  /** 切换收藏排序方式（time / category / title），回到第 1 页重新拉取 */
  function setFavSort(sort) {
    if (state.favs.sort === sort) return;
    state.favs.sort = sort;
    state.favs.page = 1;
    loadFavorites();
  }

  /** 收藏页取消收藏：先二次确认（防误点），成功后重拉当前页；本页已空且非首页则自动回退一页 */
  async function cancelFav(item) {
    const id = item.resource_id ?? item.id;
    if (item._busy) return;                       // 防连点
    try {
      await ElMessageBox.confirm(
        `确定取消收藏《${item.title}》？该资源会从收藏列表移除。`
        + '你的浏览、评分等行为记录与推荐结果不受影响，之后仍可重新收藏。',
        '取消收藏', { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '再想想' });
    } catch (e) {
      return;                                     // 用户点了「再想想」或关闭弹窗：不做任何改动
    }
    item._busy = true;
    try {
      const r = await A.removeFavorite(id);
      if (r.detail) return ElMessage.error(r.detail);
      ElMessage.success('已取消收藏');
      if (state.detail.info && state.detail.info.id === id) state.detail.info.favorited = false;
      if (state.favs.items.length <= 1 && state.favs.page > 1) state.favs.page -= 1;
      await loadFavorites();
    } catch (e) {
      ElMessage.error('取消收藏失败，请稍后重试');
    } finally { item._busy = false; }
  }

  async function loadStats() {
    try {
      state.stats = await A.dashboard();
    } catch (e) { ElMessage.error('加载统计失败，请稍后重试'); }
  }

  /** 学生凭邀请码升级为教师：换发令牌、更新本地身份，历史数据不变。
   *  失败统一抛带可读 message 的 Error（调用点负责提示），避免网络异常裸抛到界面。 */
  async function upgradeToTeacher(invite_code) {
    let r;
    try {
      r = await A.upgradeToTeacher(invite_code);
    } catch (e) {
      throw new Error('网络异常，请检查连接后重试');
    }
    if (r.detail) throw new Error(typeof r.detail === 'string' ? r.detail : '升级失败');
    persistLogin(r);                       // 新令牌（role 已变更）
    ElMessage.success(r.message);
    return r;
  }

  // ---- 消息通知 ----
  async function loadNotifications() {
    if (!state.me.user_id) return;
    try {
      const r = await A.notifications();
      state.notif.items = r.items || [];
      state.notif.unread = r.unread || 0;
    } catch (e) { /* 静默 */ }
  }
  async function markNotifRead(id) {
    try {
      await A.markNotifRead(id);
      loadNotifications();
    } catch (e) { /* 静默：单条已读失败不阻塞列表 */ }
  }
  async function readAllNotifications() {
    try {
      await A.readAllNotifications();
      ElMessage.success('已全部标记为已读');
      loadNotifications();
    } catch (e) { ElMessage.error('操作失败，请稍后重试'); }
  }

  // ---- 学习画像 ----
  async function loadPortrait() {
    try {
      const r = await A.portrait();
      state.portrait = r;
    } catch (e) { /* 静默 */ }
  }

  const TAB_PATH = { recommend: '/recommend', resources: '/search',
                     profile: '/profile', teacher: '/teacher', admin: '/admin' };

  function onTab(name) {
    // 各页签数据由组件挂载时自行加载（lazy 渲染），这里仅负责 URL 同步
    if (TAB_PATH[name] && window.App.navigate) window.App.navigate(TAB_PATH[name]);
  }

  window.App.store = {
    state, doLogin, doRegister, saveInterests, updateProfile, doLogout, FAV_PAGE_SIZE,
    loadRec, loadHot, search, rate, fav, view, openDetail,
    loadHistory, removeHistory, loadFavorites, setFavSort, cancelFav, loadStats, onTab,
    loadNotifications, markNotifRead, readAllNotifications, loadPortrait, upgradeToTeacher,
    ROLE_NAME,
  };
})();
