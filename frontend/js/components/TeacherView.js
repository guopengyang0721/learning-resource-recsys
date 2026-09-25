/** 教师工作台（教师/管理员）：上传资源（真实署名）+ 我的上传（编辑/删除/热度统计） */
(function () {
  const { ref } = window.Vue;
  const { ElMessage, ElMessageBox } = window.ElementPlus;
  const C = window.App.components = window.App.components || {};
  const A = window.App.api;
  const TYPE_NAME = { video: '视频', doc: '文档', ppt: '课件', question: '题库', book: '书籍', course: '系列课' };

  C.TeacherView = {
    setup() {
      const items = ref([]);
      const uploadVisible = ref(false);
      const editVisible = ref(false);
      const form = ref({ title: '', type: 'doc', category: '软件工程', difficulty: 3, description: '', url: '',
                         file_name: '', file_size: 0, file_path: '' });
      const editId = ref(null);
      const editWasOnline = ref(false);     // 编辑对象是否原为已上架（决定弹窗顶部提示）
      const uploading = ref(false);
      const pendingFile = ref(null);       // 待上传的本地文件（拖拽/选择后暂存，提交时才真正上传）
      const uploadRef = ref(null);          // el-upload 实例（用于切换资源时清空文件列表）
      const isAdmin = window.App.store.state.me.role === 'admin';

      const categories = ['软件工程', '机器学习', '数据库', '计算机网络', '算法', 'Web开发', '人工智能', '其他'];
      const ACCEPT = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.csv,.zip,.rar,.7z,.mp4,.mp3,.wav,.png,.jpg,.jpeg,.gif';

      /** 字节 → 易读大小 */
      function fmtSize(n) {
        if (!n) return '0 B';
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(0) + ' KB';
        return (n / 1024 / 1024).toFixed(1) + ' MB';
      }
      function onFileChange(f) {
        pendingFile.value = f.raw || f;      // el-upload 的条目对象里 raw 才是原生 File
      }
      function onFileRemove() { pendingFile.value = null; }
      function onExceed() { ElMessage.warning('一次只能上传一个文件，请先移除已选文件'); }
      /** 切换上传/编辑对象时清空 el-upload 内部文件列表（避免残留上一个资源的文件名） */
      function clearUploadList() {
        window.Vue.nextTick(() => { if (uploadRef.value) uploadRef.value.clearFiles(); });
      }

      async function load() {
        try {
          const r = await A.myResources();
          items.value = r.items || [];
        } catch (e) { ElMessage.error('我的资源加载失败，请刷新重试'); }
      }
      function openUpload() {
        form.value = { title: '', type: 'doc', category: '软件工程', difficulty: 3, description: '', url: '',
                       file_name: '', file_size: 0, file_path: '' };
        editId.value = null;
        pendingFile.value = null;
        uploadVisible.value = true;
        clearUploadList();
      }
      function openEdit(row) {
        editId.value = row.id;
        editWasOnline.value = row.status === 'online';   // 已上架资源编辑后将回待审核（弹窗顶部提示）
        form.value = { title: row.title, type: row.type, category: row.category,
                       difficulty: row.difficulty, description: row.description || '',
                       url: row.url || '',
                       file_name: row.file_name || '', file_size: row.file_size || 0,
                       file_path: row.file_path || '' };
        pendingFile.value = null;            // 不重选则保留原附件
        uploadVisible.value = true;
        clearUploadList();
      }
      async function submit() {
        if (uploading.value) return;                       // 防连点重复提交（含文件上传期间）
        if (!form.value.title.trim()) return ElMessage.warning('请填写资源标题');
        const u = (form.value.url || '').trim();
        if (u && !/^https?:\/\/.+/i.test(u)) return ElMessage.warning('资源链接需以 http:// 或 https:// 开头');
        form.value.url = u;
        // 拖拽不受 accept 限制，提交前再校验一次类型与体积（与后端白名单一致）
        const f = pendingFile.value;
        if (f) {
          if (f.size > 50 * 1024 * 1024) return ElMessage.warning('文件不能超过 50MB');
          const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
          if (!ACCEPT.split(',').includes(ext)) return ElMessage.warning('不支持的文件类型：' + ext);
        }
        uploading.value = true;
        try {
          // 选了本地文件：先上传拿到存储路径，再连同表单一起提交资源
          if (pendingFile.value) {
            const up = await A.uploadFile(pendingFile.value);
            if (up.detail || !up.file_path) {
              ElMessage.error(up.detail || '文件上传失败，请重试');
              return;
            }
            form.value.file_name = up.file_name;
            form.value.file_size = up.file_size;
            form.value.file_path = up.file_path;
            pendingFile.value = null;   // 文件已上传成功（路径已入 form），提交失败重试时不再重复上传
          }
          const r = editId.value
            ? await A.updateResource(editId.value, form.value)
            : await A.uploadResource(form.value);
          if (r.detail) return ElMessage.error(r.detail);
          ElMessage.success(r.message);
          uploadVisible.value = false;
          pendingFile.value = null;
          load();
        } finally {
          uploading.value = false;                         // 任何路径（成功/失败/提前返回）都复位
        }
      }
      function del(row) {
        ElMessageBox.confirm(`确定删除自己上传的《${row.title}》？`, '确认删除', { type: 'warning' })
          .then(async () => {
            try {
              const r = await A.deleteOwnResource(row.id);
              if (r.detail) return ElMessage.error(r.detail);
              ElMessage.success(r.message);
              load();
            } catch (e) { ElMessage.error('删除失败，请稍后重试'); }
          })
          .catch(() => {});
      }

      return { items, uploadVisible, form, editId, openUpload, openEdit, submit, del, load,
               uploading, pendingFile, onFileChange, onFileRemove, onExceed, fmtSize, ACCEPT,
               uploadRef,
               categories, TYPE_NAME, isAdmin, editWasOnline };
    },
    mounted() { this.load(); },
    template: `
    <div>
      <el-card shadow="never" :body-style="{padding:'10px 16px'}">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <div style="color:#666;font-size:13px">
            上传的资源将署你的名字{{ isAdmin ? '（管理员上传直接上架）' : '，提交后需管理员审核上架' }}
          </div>
          <el-button type="primary" @click="openUpload">⬆ 上传新资源</el-button>
        </div>
      </el-card>

      <el-card style="margin-top:12px" :body-style="{padding:'12px'}">
        <el-row :gutter="12">
          <el-col v-for="it in items" :key="it.id" :xs="24" :sm="12" :md="8" style="margin-bottom:12px">
            <el-card shadow="hover" :body-style="{padding:'14px'}">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b style="font-size:14px">{{ it.title }}</b>
                <el-tag size="small" :type="it.status==='online' ? 'success' : (it.status==='pending' ? 'warning' : 'info')">
                  {{ it.status==='online' ? '已上架' : (it.status==='pending' ? '待审核' : '已下架') }}
                </el-tag>
              </div>
              <div style="color:#666;font-size:12px;margin:8px 0">
                <el-tag size="small">{{ it.category }}</el-tag>
                <el-tag size="small" type="success" style="margin-left:6px">{{ TYPE_NAME[it.type] || it.type }}</el-tag>
                <el-tag size="small" type="warning" style="margin-left:6px">难度 {{ it.difficulty }}/5</el-tag>
              </div>
              <div style="color:#98a5bd;font-size:12px">
                🔥 点击 {{ it.click_count }} · ⭐ 平均分 {{ it.avg_score }}（{{ it.ratings }} 人评）· {{ it.created_at }}
              </div>
              <div style="font-size:12px;margin-top:3px">
                <span v-if="it.url" style="color:#67c23a">🔗 已附资源链接</span>
                <span v-else style="color:#e6a23c">⚠️ 未附链接（学生端无「去学习」按钮）</span>
                <div v-if="it.has_file" style="color:#409eff;margin-top:2px;word-break:break-all">
                  📎 {{ it.file_name }}（{{ fmtSize(it.file_size) }}）
                </div>
                <div v-else style="color:#c0c4cc;margin-top:2px">未上传附件文件</div>
              </div>
              <div style="margin-top:8px">
                <el-button size="small" type="primary" plain @click="openEdit(it)">编 辑</el-button>
                <el-button size="small" type="danger" plain @click="del(it)">删 除</el-button>
              </div>
            </el-card>
          </el-col>
        </el-row>
        <el-empty v-if="!items.length" description="还没有上传过资源，点右上角「上传新资源」开始"></el-empty>
      </el-card>

      <!-- 上传/编辑弹窗 -->
      <el-dialog v-model="uploadVisible" :title="editId ? '✏️ 编辑资源' : '⬆ 上传新资源'" width="520px">
        <el-alert v-if="editId && editWasOnline && !isAdmin" type="warning" :closable="false"
                  title="该资源已上架：保存修改后将暂时下架，待管理员重新审核通过再上架" style="margin-bottom:10px"></el-alert>
        <el-form label-width="80px">
          <el-form-item label="标题">
            <el-input v-model="form.title" maxlength="200" placeholder="资源标题"></el-input>
          </el-form-item>
          <el-form-item label="类型">
            <el-radio-group v-model="form.type">
              <el-radio-button v-for="(name, key) in TYPE_NAME" :key="key" :value="key">{{ name }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="分类">
            <el-select v-model="form.category" style="width:100%">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c"></el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="难度">
            <el-rate v-model="form.difficulty" :max="5"></el-rate>
          </el-form-item>
          <el-form-item label="简介">
            <el-input v-model="form.description" type="textarea" :rows="3" placeholder="资源简介（展示在详情页）"></el-input>
          </el-form-item>
          <el-form-item label="资源链接">
            <el-input v-model="form.url" maxlength="300" clearable
                      placeholder="选填，如 https://...（学生可在详情页一键跳转）"></el-input>
            <div style="color:#98a5bd;font-size:12px;line-height:1.6;margin-top:4px">
              留空也可提交：详情页将不显示「去学习」按钮。建议粘贴课程主页 / 文档地址等可公开访问的链接。
            </div>
          </el-form-item>
          <el-form-item label="资源文件">
            <el-upload ref="uploadRef" drag :auto-upload="false" :limit="1" :accept="ACCEPT"
                       :on-change="onFileChange" :on-remove="onFileRemove" :on-exceed="onExceed"
                       style="width:100%">
              <div style="padding:10px 0;color:#666;font-size:13px">
                <div style="font-size:26px">📁</div>
                <div>把文件拖到这里，或 <em style="color:#409eff;font-style:normal">点击选择文件</em></div>
                <div style="color:#98a5bd;font-size:12px;margin-top:4px">
                  单个文件 ≤ 50MB；支持 PDF / Office 文档 / 课件 / 音视频 / 压缩包
                </div>
              </div>
            </el-upload>
            <div v-if="editId && form.file_name && !pendingFile"
                 style="color:#67c23a;font-size:12px;margin-top:4px;word-break:break-all">
              📎 当前附件：{{ form.file_name }}（不重新选择则保留）
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="uploadVisible = false">取消</el-button>
          <el-button type="primary" :loading="uploading" @click="submit">
            {{ editId ? '保存修改' : '提 交' }}{{ uploading ? '（文件上传中…）' : '' }}
          </el-button>
        </template>
      </el-dialog>
    </div>`
  };
})();
