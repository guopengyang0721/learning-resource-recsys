/** 个人中心视图：内部子页导航（个人信息 / 我的足迹 / 我的收藏），每页全宽展示 */
(function () {
  const C = window.App.components = window.App.components || {};

  C.ProfileView = {
    setup() {
      const { ref, watch, nextTick, onBeforeUnmount, computed } = window.Vue;
      const { ElMessage } = window.ElementPlus;
      const { state, openDetail, removeHistory, loadHistory, loadFavorites,
              saveInterests, updateProfile, loadPortrait, upgradeToTeacher, onTab } = window.App.store;
      const A = window.App.api;
      const SEC_QUESTIONS = ['你的第一所学校是？', '你最喜欢的课程是？', '你母亲的名字是？',
                             '你最好的朋友的名字是？', '你的出生城市是？'];
      const ROLE_NAME = window.App.store.ROLE_NAME || {};
      const roleName = (r) => ROLE_NAME[r] || r;                      // 角色显示中文（判断仍用英文）
      const FAV_PAGE_SIZE = 12;                          // 每页收藏数：3 列 × 4 行，需与 api.myFavorites 的默认 size 一致
      const interests = computed(() => (state.me.interests || []).filter(Boolean));
      const section = ref('info');                       // info | history | favs
      const editVisible = ref(false);
      const editInterests = ref([]);
      const profileVisible = ref(false);
      const profileForm = ref({ nickname: '', gender: '', grade: '', college: '' });
      const pwdVisible = ref(false);
      const pwdForm = ref({ old_password: '', new_password: '', confirm: '' });
      const pwdLoading = ref(false);
      const secVisible = ref(false);
      const upVisible = ref(false);
      const upCode = ref('');
      const upLoading = ref(false);

      /** 凭邀请码升级为教师：成功后关闭弹窗并跳转教师工作台 */
      async function submitUpgrade() {
        if (upLoading.value) return;               // 防连点/回车重复提交
        if (!(upCode.value || '').trim()) return ElMessage.warning('请输入教师邀请码');
        upLoading.value = true;
        try {
          await upgradeToTeacher(upCode.value.trim());
          upVisible.value = false;
          upCode.value = '';
          // 让用户看到成功提示后再跳转；若期间用户已手动离开个人中心则不强制拉回
          setTimeout(() => {
            if (state.route === 'main' && state.activeTab === 'profile' && state.me.role === 'teacher') {
              onTab('teacher');
            }
          }, 800);
        } catch (e) {
          ElMessage.error(e.message || '升级失败，请稍后重试');
        } finally { upLoading.value = false; }
      }
      const secForm = ref({ question: '', answer: '', password: '' });
      let radar = null;
      let radarTimers = [];            // 兜底重绘的定时器，组件卸载时统一清理

      function renderRadar() {
        const el = document.getElementById('radar');
        const dist = state.portrait.distribution || {};
        const cats = Object.keys(dist);
        if (!el || !window.echarts || !cats.length) return;
        // v-if 切换子页会重建容器 DOM：旧实例绑定的画布已脱离文档，必须 dispose 重建
        if (radar && radar.getDom() !== el) { radar.dispose(); radar = null; }
        radar = radar || echarts.init(el);
        const maxV = Math.max(...Object.values(dist)) * 1.25 + 1;
        radar.setOption({
          title: { text: '学习画像 · 行为类别分布', left: 'center', textStyle: { fontSize: 14 } },
          tooltip: {},
          radar: { indicator: cats.map(c => ({ name: c, max: maxV })), radius: '62%' },
          series: [{
            type: 'radar',
            data: [{ value: cats.map(c => dist[c]), name: '行为次数',
                     areaStyle: { opacity: .35 }, itemStyle: { color: '#409eff' } }]
          }]
        });
      }

      /** 释放雷达图与相关定时器（切走个人中心页签时） */
      function disposeRadar() {
        radarTimers.forEach(clearTimeout);
        radarTimers = [];
        if (radar) { radar.dispose(); radar = null; }
        if (weeklyChart) { weeklyChart.dispose(); weeklyChart = null; }
      }
      const scheduleRadar = () => {     // nextTick + 300ms 兜底重绘
        radarTimers.push(setTimeout(renderRadar, 0), setTimeout(renderRadar, 300));
      };

      // ---- 本周学习周报 ----
      const weekly = ref(null);
      let weeklyChart = null;
      async function loadWeekly() {
        try {
          weekly.value = await A.weekly();
          nextTick(renderWeekly);
        } catch (e) { /* 周报加载失败静默，不影响页面主体 */ }
      }
      function renderWeekly() {
        const el = document.getElementById('weekly-chart');
        const daily = (weekly.value && weekly.value.daily) || [];   // 接口结构异常时兜底为空数组
        if (!el || !window.echarts || !daily.length) return;
        if (weeklyChart && weeklyChart.getDom() !== el) { weeklyChart.dispose(); weeklyChart = null; }
        weeklyChart = weeklyChart || echarts.init(el);
        weeklyChart.setOption({
          title: { text: '近 7 天行为趋势', left: 'center', textStyle: { fontSize: 12 } },
          grid: { left: 44, right: 16, top: 40, bottom: 28 },
          tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: daily.map(d => d.date) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [{ type: 'line', name: '行为次数', smooth: true,
                     data: daily.map(d => d.count),
                     areaStyle: { opacity: .25 }, itemStyle: { color: '#409eff' } }],
        });
      }

      // 触发绘制的保障：子页切换 / 画像数据到达
      watch(section, (v) => {
        if (v === 'info') {
          loadPortrait();
          loadWeekly();
          nextTick(scheduleRadar);
        } else {
          disposeRadar();
        }
      });
      // 监听画像对象引用：每次 loadPortrait 都会整体替换，必触发（解决重挂载时值相同不触发的竞态）
      watch(() => state.portrait, () => nextTick(renderRadar));
      // 窗口缩放时重绘（保存引用，卸载时解绑，避免监听器累积泄漏）
      const onWinResize = () => { renderRadar(); renderWeekly(); };
      window.addEventListener('resize', onWinResize);
      // 组件卸载（切走个人中心页签）：清定时器/释放图表/解绑 window 监听，避免泄漏
      onBeforeUnmount(() => {
        window.removeEventListener('resize', onWinResize);
        disposeRadar();
      });

      function openEdit() {
        editInterests.value = (state.me.interests || []).filter(Boolean);
        editVisible.value = true;
      }
      async function submitInterests() {
        const ok = await saveInterests(editInterests.value);
        if (ok) editVisible.value = false;      // 失败时保留弹窗，避免丢失已勾选内容
      }
      function openProfile() {
        profileForm.value = { nickname: state.me.nickname || '', gender: state.me.gender || '保密',
                              grade: state.me.grade || '', college: state.me.college || '' };
        profileVisible.value = true;
      }
      async function submitProfile() {
        const f = profileForm.value;
        if (!f.nickname.trim()) return ElMessage.warning('昵称不能为空');
        try {
          const r = await updateProfile({ nickname: f.nickname.trim(), gender: f.gender,
                                          grade: f.grade.trim(), college: f.college.trim() });
          if (r && !r.detail) profileVisible.value = false;   // 服务端校验失败时保留输入
        } catch (e) { ElMessage.error('保存失败，请检查网络后重试'); }
      }
      function openPwd() {
        pwdForm.value = { old_password: '', new_password: '', confirm: '' };
        pwdVisible.value = true;
      }
      async function submitPwd() {
        const f = pwdForm.value;
        if (!f.old_password) return ElMessage.warning('请输入当前密码');
        if (f.new_password.length < 6) return ElMessage.warning('新密码至少 6 位');
        if (f.new_password !== f.confirm) return ElMessage.warning('两次输入的新密码不一致');
        pwdLoading.value = true;
        try {
          const r = await A.changePassword(f.old_password, f.new_password);
          if (r.detail) return ElMessage.error(r.detail);
          ElMessage.success(r.message);
          pwdVisible.value = false;
        } catch (e) {
          ElMessage.error('修改失败，请检查网络后重试');
        } finally { pwdLoading.value = false; }
      }
      function changeFavPage(p) { loadFavorites(p); }
      function openSec() {
        secForm.value = { question: '', answer: '', password: '' };
        secVisible.value = true;
      }
      const secLoading = ref(false);
      async function submitSec() {
        if (secLoading.value) return;              // 防连点（涉及身份确认，避免并发请求）
        const f = secForm.value;
        if (!f.question) return ElMessage.warning('请选择密保问题');
        if (!f.answer.trim()) return ElMessage.warning('请输入密保答案');
        if (!f.password) return ElMessage.warning('请输入当前密码以确认身份');
        secLoading.value = true;
        try {
          const r = await A.setSecurityQuestion({ question: f.question, answer: f.answer.trim(), password: f.password });
          if (r.detail) return ElMessage.error(r.detail);
          state.me.has_sec_question = true;
          window.App.saveMe(state.me);
          ElMessage.success(r.message);
          secVisible.value = false;
        } catch (e) {
          ElMessage.error('设置失败，请稍后重试');
        } finally { secLoading.value = false; }
      }

      /** 「账号设置」下拉的指令分发 */
      function onAccountCmd(cmd) {
        if (cmd === 'pwd') openPwd();
        else if (cmd === 'sec') openSec();
        else if (cmd === 'upgrade') upVisible.value = true;
      }

      return { s: state, section, openDetail, removeHistory, loadHistory, loadFavorites, changeFavPage,
               roleName, interests, onAccountCmd, FAV_PAGE_SIZE,
               editVisible, editInterests, openEdit, submitInterests, loadPortrait, weekly, loadWeekly,
               profileVisible, profileForm, openProfile, submitProfile,
               pwdVisible, pwdForm, pwdLoading, openPwd, submitPwd,
               secVisible, secForm, openSec, submitSec, SEC_QUESTIONS,
               upVisible, upCode, upLoading, submitUpgrade };
    },
    // 数据加载改用 setup 内 onMounted 闭包直调（不经过 this，避免 return 漏函数导致静默失效）
    mounted() { this.loadHistory(); this.loadFavorites(); this.loadPortrait(); this.loadWeekly(); },
    template: `
    <div>
      <!-- 子页导航 -->
      <el-card shadow="never" :body-style="{padding:'10px 16px'}">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <el-radio-group v-model="section">
            <el-radio-button value="info">👤 个人信息</el-radio-button>
            <el-radio-button value="history">🕘 我的足迹</el-radio-button>
            <el-radio-button value="favs">⭐ 我的收藏</el-radio-button>
          </el-radio-group>
          <div style="color:#98a5bd;font-size:13px">
            共收藏 <b style="color:#409eff">{{ s.favs.total }}</b> 条资源 ·
            行为记录 <b style="color:#409eff">{{ s.history.items.length }}</b> 条
          </div>
        </div>
      </el-card>

      <!-- ===== 子页：个人信息 ===== -->
      <div v-if="section === 'info'" style="margin-top:12px">
        <el-card>
          <div style="display:flex;align-items:flex-start;gap:22px;flex-wrap:wrap">
            <div style="width:88px;height:88px;border-radius:50%;flex:none;
                        background:linear-gradient(135deg,#409eff,#2fa58a);
                        display:flex;align-items:center;justify-content:center;font-size:42px;
                        box-shadow:0 4px 14px rgba(64,158,255,.22)">🎓</div>

            <div style="flex:1;min-width:260px">
              <!-- 昵称 + 角色 + 兴趣状态 -->
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <h2 style="margin:0;font-size:21px;line-height:1.3">{{ s.me.nickname }}</h2>
                <el-tag size="small" effect="plain">{{ roleName(s.me.role) }}</el-tag>
                <el-tag v-if="interests.length" type="success" size="small" effect="plain">已设置兴趣</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">未设置兴趣</el-tag>
              </div>
              <div style="color:#98a5bd;font-size:13px;margin-top:7px">
                {{ s.me.username }} · ID {{ s.me.user_id }}
              </div>

              <!-- 基本信息：用分隔点排列，避免"标签：值"竖向堆叠 -->
              <div style="margin-top:12px;font-size:13px;color:#909399;display:flex;align-items:center;gap:14px;flex-wrap:wrap">
                <span>性别 <b style="color:#303133">{{ s.me.gender || '保密' }}</b></span>
                <span style="color:#e4e7ed">|</span>
                <span>年级 <b style="color:#303133">{{ s.me.grade || '未填写' }}</b></span>
                <span style="color:#e4e7ed">|</span>
                <span>学院 <b style="color:#303133">{{ s.me.college || '未填写' }}</b></span>
              </div>

              <!-- 兴趣标签 -->
              <div style="margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span style="font-size:13px;color:#909399">🎯 兴趣</span>
                <el-tag v-for="t in interests" :key="t" size="small" type="success">{{ t }}</el-tag>
                <span v-if="!interests.length" style="color:#c0c4cc;font-size:13px">
                  未设置 —— 设置后新账号也能获得个性化推荐
                </span>
              </div>
            </div>
          </div>

          <!-- 操作区：与信息区用细线分隔；常用操作平铺，安全类操作收进「账号设置」下拉 -->
          <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--el-border-color-lighter)">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <el-button type="primary" @click="openProfile">编辑资料</el-button>
              <el-button plain @click="openEdit">编辑兴趣</el-button>

              <el-dropdown style="margin-left:auto" trigger="click" @command="onAccountCmd">
                <el-button plain>
                  账号设置<span style="margin-left:6px;font-size:12px;color:#a8abb2">▾</span>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="pwd">修改密码</el-dropdown-item>
                    <el-dropdown-item command="sec">
                      {{ s.me.has_sec_question ? '修改密保问题' : '设置密保问题' }}
                    </el-dropdown-item>
                    <el-dropdown-item v-if="s.me.role === 'student'" command="upgrade" divided>升级为教师</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div v-if="!s.me.has_sec_question" style="color:#e6a23c;font-size:12px;margin-top:10px">
              ⚠️ 尚未设置密保问题，忘记密码时只能联系管理员重置
            </div>
          </div>
        </el-card>

        <el-row :gutter="12" style="margin-top:12px">
          <el-col :xs="24" :sm="8"><el-card shadow="hover"><el-statistic title="我的收藏" :value="s.favs.total"></el-statistic></el-card></el-col>
          <el-col :xs="24" :sm="8"><el-card shadow="hover"><el-statistic title="行为记录" :value="s.history.items.length"></el-statistic></el-card></el-col>
          <el-col :xs="24" :sm="8"><el-card shadow="hover"><el-statistic title="兴趣类别" :value="(s.me.interests || []).filter(Boolean).length"></el-statistic></el-card></el-col>
        </el-row>

        <!-- 本周学习周报 -->
        <el-card style="margin-top:12px">
          <template #header><b>📅 本周学习周报</b></template>
          <el-row :gutter="12" v-if="weekly">
            <el-col :xs="24" :md="9">
              <div style="font-size:14px;line-height:2.2">
                <div>本周共 <b style="color:#409eff;font-size:18px">{{ weekly.total }}</b> 次学习行为</div>
                <div>👀 浏览 <b>{{ weekly.view }}</b> · ⭐ 收藏 <b>{{ weekly.favorite }}</b> · 🏷️ 评分 <b>{{ weekly.rate }}</b> · ⬇️ 下载 <b>{{ weekly.download }}</b></div>
                <div>覆盖 <b>{{ weekly.categories }}</b> 个分类，最活跃：<b style="color:#409eff">{{ weekly.top_category || '—' }}</b>（{{ weekly.top_category_count }} 次）</div>
              </div>
            </el-col>
            <el-col :xs="24" :md="15">
              <div id="weekly-chart" style="width:100%;height:190px"></div>
            </el-col>
          </el-row>
          <el-skeleton v-else :rows="2" animated></el-skeleton>
        </el-card>

        <el-row :gutter="12" style="margin-top:12px">
          <el-col :xs="24" :md="14">
            <el-card>
              <div id="radar" style="width:100%;height:300px"
                   v-if="Object.keys(s.portrait.distribution || {}).length"></div>
              <el-empty v-else description="暂无行为数据——去浏览、收藏、评分一些资源，生成你的学习画像吧"
                        :image-size="80"></el-empty>
            </el-card>
          </el-col>
          <el-col :xs="24" :md="10">
            <el-card header="📈 画像解读">
              <div style="color:#666;font-size:13px;line-height:2">
                <template v-if="Object.keys(s.portrait.distribution || {}).length">
                  · 你的行为共覆盖 <b>{{ Object.keys(s.portrait.distribution).length }}</b> 个资源类别；<br/>
                  · 最活跃类别：<b style="color:#409eff">{{ (Object.entries(s.portrait.distribution).sort((a,b)=>b[1]-a[1])[0]||[])[0] || '-' }}</b>；<br/>
                  · 雷达图面积越大，说明你在该类资源上投入越多，推荐引擎也会相应加大此类资源的权重。
                </template>
                <template v-else>行为数据是推荐的燃料——你的每一条浏览/收藏/评分都会实时写入推荐引擎的训练数据。</template>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card header="💡 说明" style="margin-top:12px">
          <div style="color:#666;font-size:13px;line-height:2">
            · 每次浏览、收藏、评分都会被行为采集模块记录，作为协同过滤推荐的输入；<br/>
            · 行为较少时，系统会按你设置的兴趣类别做冷启动推荐，行为积累后自动过渡到纯协同过滤；<br/>
            · 修改密码后下次登录请使用新密码。
          </div>
        </el-card>
      </div>

      <!-- ===== 子页：我的足迹 ===== -->
      <div v-else-if="section === 'history'" class="profile-subpage" style="margin-top:12px">
        <el-card>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
            <div style="color:#666;font-size:13px">
              你最近的浏览 / 收藏 / 评分记录（{{ s.history.items.length }} 条），这些数据是个性化推荐的依据
            </div>
            <el-button size="small" @click="loadHistory">🔄 刷新</el-button>
          </div>
          <el-table :data="s.history.items" size="small" max-height="520">
            <el-table-column prop="time" label="时间" width="150"></el-table-column>
            <el-table-column prop="action_name" label="行为" width="90">
              <template #default="scope">
                <el-tag size="small" :type="scope.row.action==='rate' ? 'warning' : (scope.row.action==='favorite' ? 'success' : 'info')">
                  {{ scope.row.action_name }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="资源" min-width="260"></el-table-column>
            <el-table-column prop="category" label="分类" width="110"></el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="scope">
                <el-button size="small" text type="primary"
                           @click="openDetail({ id: scope.row.resource_id, title: scope.row.title })">详情</el-button>
                <el-button size="small" text type="danger"
                           @click="removeHistory(scope.row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="color:#999;font-size:12px;margin-top:8px">
            删除记录只影响历史展示，已计入的训练数据在模型下次离线重训练前仍然有效。
          </div>
        </el-card>
      </div>

      <!-- ===== 子页：我的收藏 ===== -->
      <div v-else class="profile-subpage" style="margin-top:12px">
        <el-card>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
            <div style="color:#666;font-size:13px">共 {{ s.favs.total }} 条收藏，点击卡片查看详情</div>
            <el-button size="small" @click="loadFavorites">🔄 刷新</el-button>
          </div>
          <el-row :gutter="12" class="fav-grid">
            <el-col v-for="f in s.favs.items" :key="f.resource_id" :xs="24" :sm="12" :md="8" style="margin-bottom:12px">
              <el-card shadow="hover" @click="openDetail(f)" :body-style="{padding:'14px'}">
                <b style="font-size:14px">{{ f.title }}</b>
                <div style="color:#666;font-size:12px;margin:8px 0">
                  <el-tag size="small">{{ f.category }}</el-tag>
                  <el-tag size="small" type="success" style="margin-left:6px">{{ f.type }}</el-tag>
                  <el-tag size="small" type="warning" style="margin-left:6px">难度 {{ f.difficulty }}/5</el-tag>
                </div>
                <div style="color:#999;font-size:12px">⭐ 收藏于 {{ f.time }}</div>
              </el-card>
            </el-col>
          </el-row>
          <el-empty v-if="!s.favs.items.length" description="暂无收藏，去「资源检索」页发现好资源吧"></el-empty>
          <el-pagination v-if="s.favs.total > s.favs.items.length || s.favs.total > FAV_PAGE_SIZE"
                         class="pager-bottom" layout="total, prev, pager, next, jumper"
                         :total="s.favs.total" :page-size="FAV_PAGE_SIZE"
                         :current-page="s.favs.page" @current-change="changeFavPage"></el-pagination>
        </el-card>
      </div>

      <!-- 编辑资料弹窗 -->
      <el-dialog v-model="profileVisible" title="📝 编辑个人资料" width="440px">
        <el-form label-width="90px">
          <el-form-item label="昵称">
            <el-input v-model="profileForm.nickname" maxlength="50"></el-input>
          </el-form-item>
          <el-form-item label="性别">
            <el-radio-group v-model="profileForm.gender">
              <el-radio value="男">男</el-radio>
              <el-radio value="女">女</el-radio>
              <el-radio value="保密">保密</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="年级">
            <el-input v-model="profileForm.grade" maxlength="20" placeholder="如 2024级"></el-input>
          </el-form-item>
          <el-form-item label="学院">
            <el-input v-model="profileForm.college" maxlength="50" placeholder="如 信息科学与技术学院"></el-input>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="profileVisible = false">取消</el-button>
          <el-button type="primary" @click="submitProfile">保存</el-button>
        </template>
      </el-dialog>

      <!-- 修改密码弹窗 -->
      <el-dialog v-model="pwdVisible" title="🔑 修改密码" width="420px">
        <el-form label-width="90px">
          <el-form-item label="当前密码">
            <el-input v-model="pwdForm.old_password" type="password" show-password></el-input>
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位"></el-input>
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="pwdForm.confirm" type="password" show-password></el-input>
          </el-form-item>
        </el-form>
        <div style="color:#98a5bd;font-size:12px">
          修改成功后当前登录不受影响，下次登录请使用新密码。
        </div>
        <template #footer>
          <el-button @click="pwdVisible = false">取消</el-button>
          <el-button type="primary" :loading="pwdLoading" @click="submitPwd">确认修改</el-button>
        </template>
      </el-dialog>

      <!-- 密保问题设置弹窗 -->
      <el-dialog v-model="secVisible" title="🔒 密保问题设置" width="440px">
        <div style="color:#666;font-size:13px;margin-bottom:12px">
          设置后忘记密码时可在登录页自助找回（需回答密保问题）。
        </div>
        <el-form label-width="90px">
          <el-form-item label="密保问题">
            <el-select v-model="secForm.question" style="width:100%" placeholder="选择密保问题">
              <el-option v-for="q in SEC_QUESTIONS" :key="q" :label="q" :value="q"></el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="答案">
            <el-input v-model="secForm.answer" maxlength="64" placeholder="答案（不区分大小写）"></el-input>
          </el-form-item>
          <el-form-item label="当前密码">
            <el-input v-model="secForm.password" type="password" show-password placeholder="输入当前密码确认身份"></el-input>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="secVisible = false">取消</el-button>
          <el-button type="primary" :loading="secLoading" @click="submitSec">保 存</el-button>
        </template>
      </el-dialog>

      <!-- 升级为教师弹窗 -->
      <el-dialog v-model="upVisible" title="👨‍🏫 升级为教师身份" width="440px">
        <div style="color:#666;font-size:13px;line-height:1.8;margin-bottom:12px">
          凭管理员发放的<b>一次性教师邀请码</b>即可升级为教师，获得上传与管理资源的权限。<br>
          你的评分、收藏、浏览足迹等<b style="color:#409eff">全部历史数据都会保留</b>，推荐体验不受影响。
        </div>
        <el-input v-model="upCode" maxlength="16" size="large" clearable
                  placeholder="输入教师邀请码（如 BD016182）" @keyup.enter="submitUpgrade">
          <template #prefix>🎟️</template>
        </el-input>
        <template #footer>
          <el-button @click="upVisible = false">取消</el-button>
          <el-button type="primary" :loading="upLoading" @click="submitUpgrade">确认升级</el-button>
        </template>
      </el-dialog>

      <!-- 编辑兴趣弹窗 -->
      <el-dialog v-model="editVisible" title="🎯 编辑兴趣类别" width="460px">
        <div style="color:#666;font-size:13px;margin-bottom:10px">
          更新后系统会立即重训练推荐模型：行为较少时按兴趣做冷启动推荐，行为多了自动过渡到协同过滤。
        </div>
        <el-checkbox-group v-model="editInterests">
          <el-checkbox v-for="c in s.categories" :key="c" :value="c">{{ c }}</el-checkbox>
        </el-checkbox-group>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" @click="submitInterests">保存并重新推荐</el-button>
        </template>
      </el-dialog>
    </div>`
  };
})();
