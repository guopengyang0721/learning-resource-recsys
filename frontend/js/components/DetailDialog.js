/** 资源详情弹窗：详情信息 + 附件下载 + "看了又看"（Item-CF 相似资源），点相似项可继续跳转查看 */
(function () {
  const { ElMessage } = window.ElementPlus;
  const C = window.App.components = window.App.components || {};

  C.DetailDialog = {
    setup() {
      const { state, openDetail, rate, fav } = window.App.store;
      /** 打开资源原始页面（新标签页，不中断浏览）。仅放行 http/https，防 javascript: 等伪协议注入 */
      function goLearn(url) {
        if (url && /^https?:\/\//i.test(url)) window.open(url, '_blank', 'noopener');
      }
      function fmtSize(n) {
        if (!n) return '0 B';
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(0) + ' KB';
        return (n / 1024 / 1024).toFixed(1) + ' MB';
      }
      /** 判断链接是否为平台检索页（课程类资源无唯一官方页时用站内搜索定位） */
      function isSearchLink(url) {
        return /search|problemset|problem\/list/i.test(url || '');
      }
      let downloadBusy = false;
      /** 下载附件：接口需要登录态，故用 fetch 带令牌取 blob 再触发保存 */
      async function download(info) {
        if (downloadBusy) return;                 // 防连点：并发多次下载
        downloadBusy = true;
        try {
          const me = window.App.readMe ? window.App.readMe() : null;
          const res = await fetch('/api/resources/' + info.id + '/download', {
            headers: me && me.token ? { Authorization: 'Bearer ' + me.token } : {},
          });
          if (res.status === 401) {                       // 令牌过期：与 api 层同口径，清态回登录页
            sessionStorage.removeItem('me'); localStorage.removeItem('me');
            location.reload();
            return;
          }
          if (!res.ok) {
            const b = await res.json().catch(() => ({}));
            const d = b.detail !== undefined ? (window.App.normDetail ? window.App.normDetail(b.detail) : b.detail) : '下载失败';
            ElMessage.error(d);
            return;
          }
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = info.file_name || 'resource';
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);   // 立即 revoke 在 Firefox 下可能中断下载
          ElMessage.success('已开始下载：' + (info.file_name || ''));
        } catch (e) {
          ElMessage.error('下载失败，请检查网络后重试');
        } finally {
          downloadBusy = false;
        }
      }
      return { s: state, openDetail, rate, fav, goLearn, download, fmtSize, isSearchLink,
               typeName: t => ({ video: '视频', doc: '文档', ppt: '课件', question: '题库', book: '书籍', course: '系列课' }[t] || t) };
    },
    template: `
    <el-dialog v-model="s.detail.visible" :title="s.detail.info ? ('📄 ' + s.detail.info.title) : '资源详情'"
               width="620px" top="8vh" destroy-on-close>
      <div v-if="s.detail.loading" style="text-align:center;padding:30px 0;color:#999">
        <el-icon class="is-loading">⏳</el-icon> 加载中...
      </div>
      <template v-else-if="s.detail.info">
        <div style="margin-bottom:10px">
          <el-tag size="small">{{ s.detail.info.category }}</el-tag>
          <el-tag size="small" type="success" style="margin-left:6px">{{ typeName(s.detail.info.type) }}</el-tag>
          <el-tag size="small" type="warning" style="margin-left:6px">难度 {{ s.detail.info.difficulty }}/5</el-tag>
          <el-tag size="small" type="danger" style="margin-left:6px">平均分 {{ s.detail.info.avg_score }}</el-tag>
          <el-tag size="small" type="info" style="margin-left:6px">热度 {{ s.detail.info.click_count }}</el-tag>
        </div>
        <p style="color:#555;line-height:1.8">{{ s.detail.info.description }}</p>
        <div v-if="s.detail.info.url || s.detail.info.has_file" style="margin:12px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <el-button v-if="s.detail.info.url" type="primary" @click="goLearn(s.detail.info.url)">
            🔗 去学习（打开资源页）
          </el-button>
          <el-button v-if="s.detail.info.has_file" type="success" @click="download(s.detail.info)">
            ⬇ 下载附件（{{ fmtSize(s.detail.info.file_size) }}）
          </el-button>
          <span v-if="s.detail.info.file_name" style="color:#98a5bd;font-size:12px;word-break:break-all">
            📎 {{ s.detail.info.file_name }}
          </span>
        </div>
        <div v-if="s.detail.info.url" style="color:#c0c4cc;font-size:12px;word-break:break-all;margin:-4px 0 8px">
          {{ s.detail.info.url }}
          <span v-if="isSearchLink(s.detail.info.url)" style="color:#e6a23c">
            （平台检索页：打开后为该资源的搜索结果，可从中选择具体课程/视频）
          </span>
        </div>
        <div style="margin:10px 0 4px">
          <span style="font-size:13px;color:#666;margin-right:8px">快速评价：</span>
          <el-rate size="small" @change="v=>rate(s.detail.info, v)"></el-rate>
          <el-button size="small" :type="s.detail.info.favorited ? 'success' : 'primary'"
                     :plain="!s.detail.info.favorited" style="margin-left:12px"
                     @click="fav(s.detail.info)">
            {{ s.detail.info.favorited ? '★ 已收藏（点击取消）' : '☆ 收藏' }}
          </el-button>
        </div>
        <el-divider></el-divider>
        <h4 style="margin:4px 0 10px">👀 看了又看（相似资源推荐）</h4>
        <div v-if="!s.detail.similar.length" style="color:#999;font-size:13px">
          暂无足够行为数据计算相似资源
        </div>
        <div v-for="it in s.detail.similar" :key="it.resource_id"
             style="padding:8px 10px;border:1px solid #eef1f6;border-radius:8px;margin-bottom:8px;cursor:pointer"
             @click="openDetail(it)">
          <div style="display:flex;justify-content:space-between">
            <b style="font-size:13px">{{ it.title }}</b>
            <el-tag size="small" type="success">相似度 {{ it.sim }}</el-tag>
          </div>
          <div style="color:#409eff;font-size:12px;margin-top:2px">💡 {{ it.reason }}</div>
        </div>
      </template>
    </el-dialog>`
  };
})();
