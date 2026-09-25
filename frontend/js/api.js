/** 后端 API 访问封装：
 *  令牌双存储——勾选"记住我"存 localStorage（7天），否则 sessionStorage（关浏览器即失效）；
 *  每次请求自动携带令牌，服务端滑动续签的新令牌经 X-Renewed-Token 响应头下发并自动替换；
 *  收到 401 清除本地登录态回到登录页。 */
(function () {
  function readMe() {
    try {
      return JSON.parse(sessionStorage.getItem('me') || localStorage.getItem('me') || 'null');
    } catch (e) { return null; }
  }
  function getToken() { return (readMe() || {}).token || ''; }

  function saveMe(payload) {
    if (!payload) return;
    if (payload.remember) {
      localStorage.setItem('me', JSON.stringify(payload));
      sessionStorage.removeItem('me');
    } else {
      sessionStorage.setItem('me', JSON.stringify(payload));
      localStorage.removeItem('me');
    }
  }

  function renewToken(token) {
    const me = readMe();
    if (!me) return;
    me.token = token;
    saveMe(me);
    if (window.App && window.App.store) window.App.store.state.me.token = token;
  }

  function forceLogout() {
    if (!sessionStorage.getItem('me') && !localStorage.getItem('me')) return;
    sessionStorage.removeItem('me');
    localStorage.removeItem('me');
    location.reload();   // 回到登录页
  }

  // 后端校验错误（FastAPI 422 的 detail 是对象数组）统一转成中文可读字符串，
  // 保证各调用点 `if (r.detail) ElMessage.error(r.detail)` 都能显示人话
  const FIELD_CN = { username: '用户名', password: '密码', nickname: '昵称', answer: '密保答案',
                     new_password: '新密码', old_password: '旧密码', sec_question: '密保问题',
                     sec_answer: '密保答案', title: '标题', description: '简介', category: '分类',
                     type: '类型', difficulty: '难度', role: '角色', value: '值', page: '页码',
                     size: '每页条数', keyword: '关键词', status: '状态', url: '资源链接' };
  const MSG_RULES = [
    [/string should have at least (\d+) characters?/i, (m, n) => `长度不足，至少 ${n} 个字符`],
    [/string should have at most (\d+) characters?/i, (m, n) => `长度超出，最多 ${n} 个字符`],
    [/field required/i, () => '不能为空'],
    [/input should be a valid (integer|number)/i, () => '必须是数字'],
    [/string should match pattern/i, () => '格式不正确'],
    [/greater than or equal to (\d+)/i, (m, n) => `不能小于 ${n}`],
    [/less than or equal to (\d+)/i, (m, n) => `不能大于 ${n}`],
    [/input should be (.*)/i, (m, v) => `值不合法（${v}）`],
  ];
  function normDetail(detail) {
    if (typeof detail === 'string') return detail;
    if (!Array.isArray(detail)) return detail ? JSON.stringify(detail) : '请求失败';
    return detail.map((e) => {
      const field = (e.loc || []).filter((k) => !['body', 'query', 'path'].includes(k))
        .map((k) => FIELD_CN[k] || k).join('.');
      let msg = e.msg || '参数不合法';
      for (const [re, rep] of MSG_RULES) {
        if (re.test(msg)) { msg = msg.replace(re, rep); break; }
      }
      return field ? `${field}：${msg}` : msg;
    }).join('；');
  }

  /** 文件上传（multipart/form-data）——不能复用 api()，否则 Content-Type 会被覆盖成 JSON */
  async function uploadFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch('/api/teacher/resources/upload', { method: 'POST', body: fd, headers });
    if (res.status === 401) { forceLogout(); throw new Error('unauthorized'); }
    const body = await res.json().catch(() => ({}));
    if (body && body.detail) body.detail = normDetail(body.detail);
    return body;
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    // 滑动续签：服务端下发了新令牌则自动替换
    const renewed = res.headers.get('X-Renewed-Token');
    if (renewed) renewToken(renewed);
    if (res.status === 401) { forceLogout(); throw new Error('unauthorized'); }
    const body = await res.json().catch(() => ({}));
    if (!res.ok && !body.detail) {
      // 非 2xx 但无 detail（如网关 502/504 返回 HTML）也要有可读错误，避免调用点显示 "undefined"
      body.detail = '请求失败（HTTP ' + res.status + '）';
    }
    if (body && body.detail) body.detail = normDetail(body.detail);
    return body;
  }

  window.App = window.App || {};
  window.App.readMe = readMe;
  window.App.saveMe = saveMe;
  window.App.normDetail = normDetail;
  window.App.api = {
    login: (data) => api('/api/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    register: (data) => api('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),
    verify: () => api('/api/auth/verify'),
    secQuestion: (username) => api('/api/auth/sec-question', { method: 'POST', body: JSON.stringify({ username }) }),
    forgotPassword: (data) => api('/api/auth/forgot-password', { method: 'POST', body: JSON.stringify(data) }),
    setSecurityQuestion: (data) => api('/api/user/security-question', { method: 'PUT', body: JSON.stringify(data) }),
    updateInterests: (interests) => api('/api/user/interests', { method: 'PUT', body: JSON.stringify({ interests }) }),
    updateProfile: (data) => api('/api/user/profile', { method: 'PUT', body: JSON.stringify(data) }),
    changePassword: (old_password, new_password) => api('/api/user/change-password', { method: 'POST', body: JSON.stringify({ old_password, new_password }) }),
    hotList: (limit = 5) => api('/api/recommend/hot?limit=' + limit),
    recommend: (userId, { n = 10, algo = 'user_cf' } = {}) =>
      api(`/api/recommend/${userId}?n=${n}&algo=${algo}`),
    retrainModel: () => api('/api/admin/retrain', { method: 'POST' }),   // 仅管理员
    searchResources: (params) => api('/api/resources?' + new URLSearchParams(params).toString()),
    reportBehavior: (data) => api('/api/behavior', { method: 'POST', body: JSON.stringify(data) }),
    addFavorite: (resourceId) => api(`/api/favorites/${resourceId}`, { method: 'POST' }),
    removeFavorite: (resourceId) => api(`/api/favorites/${resourceId}`, { method: 'DELETE' }),
    resourceDetail: (id) => api('/api/resources/' + id),
    similarResources: (id, n = 5) => api(`/api/resources/${id}/similar?n=${n}`),
    myHistory: (limit = 50) => api('/api/user/history?limit=' + limit),
    removeHistory: (logId) => api('/api/user/history/' + logId, { method: 'DELETE' }),
    myFavorites: (page = 1) => api('/api/user/favorites?page=' + page),
    notifications: () => api('/api/user/notifications'),
    markNotifRead: (id) => api(`/api/user/notifications/${id}/read`, { method: 'POST' }),
    readAllNotifications: () => api('/api/user/notifications/read-all', { method: 'POST' }),
    portrait: () => api('/api/user/portrait'),
    weekly: () => api('/api/user/weekly'),
    compareRecommend: (n = 8) => api(`/api/recommend/compare?n=${n}`),
    dashboard: () => api('/api/admin/stats/dashboard'),
    trend: () => api('/api/admin/stats/trend'),
    adminResources: (params) => api('/api/admin/resources?' + new URLSearchParams(params)),
    setResourceStatus: (id, status) => api(`/api/admin/resources/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
    deleteResource: (id) => api(`/api/admin/resources/${id}`, { method: 'DELETE' }),
    adminUsers: (params) => api('/api/admin/users?' + new URLSearchParams(params)),
    generateInviteCode: () => api('/api/admin/users/invite-codes', { method: 'POST' }),
    inviteCodes: () => api('/api/admin/users/invite-codes'),
    upgradeToTeacher: (invite_code) => api('/api/user/upgrade-to-teacher', { method: 'POST', body: JSON.stringify({ invite_code }) }),
    /** 管理端 CSV 导出：带令牌取 blob 并触发保存（CSV 带 BOM，Excel 直开不乱码）
     *  文件名优先取服务端 Content-Disposition（含日期戳），取不到时回退到调用方传入的兜底名 */
    exportCsv: async (kind, fallbackName) => {
      const me = readMe();
      const res = await fetch('/api/admin/export/' + kind, {
        headers: me && me.token ? { Authorization: 'Bearer ' + me.token } : {},
      });
      if (res.status === 401) { forceLogout(); throw new Error('登录已过期'); }
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(normDetail(b.detail) || '导出失败');
      }
      const cd = res.headers.get('Content-Disposition') || '';
      const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
      const name = m ? decodeURIComponent(m[1].trim()) : fallbackName;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);   // 立即 revoke 在 Firefox 下可能中断下载
    },
    setUserStatus: (id, status) => api(`/api/admin/users/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
    resetUserPassword: (id, new_password) => api(`/api/admin/users/${id}/password`, { method: 'PUT', body: JSON.stringify({ new_password }) }),
    deleteUser: (id) => api('/api/admin/users/' + id, { method: 'DELETE' }),
    broadcast: (data) => api('/api/admin/notifications/broadcast', { method: 'POST', body: JSON.stringify(data) }),
    myResources: () => api('/api/teacher/my-resources'),
    uploadResource: (data) => api('/api/teacher/resources', { method: 'POST', body: JSON.stringify(data) }),
    updateResource: (id, data) => api(`/api/teacher/resources/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteOwnResource: (id) => api(`/api/teacher/resources/${id}`, { method: 'DELETE' }),
    uploadFile,
    downloadUrl: (id) => '/api/resources/' + id + '/download',
  };
})();
