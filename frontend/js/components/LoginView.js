/** 登录视图：登录 / 注册 / 忘记密码（密保问题找回）三合一 */
(function () {
  const { ElMessage } = window.ElementPlus;
  const C = window.App.components = window.App.components || {};

  const SEC_QUESTIONS = ['你的第一所学校是？', '你最喜欢的课程是？', '你母亲的名字是？',
                         '你最好的朋友的名字是？', '你的出生城市是？'];

  C.LoginView = {
    setup() {
      const { ref, watch } = window.Vue;
      const { state, doLogin, doRegister } = window.App.store;
      const A = window.App.api;
      const mode = ref('login');   // login | register | forgot
      const fpLoading = ref(false);

      // 注册身份切回学生时清掉邀请码残留，避免脏字段随请求提交
      watch(() => state.regForm.role, (r) => {
        if (r !== 'teacher') state.regForm.invite_code = '';
      });

      /** 注册前本地校验：把后端规则前移，避免"提交后才报错" */
      function submitRegister() {
        const f = state.regForm;
        const u = (f.username || '').trim();
        if (!u) return ElMessage.warning('请输入用户名');
        if (u.length < 2) return ElMessage.warning('用户名至少 2 个字符');
        if (u.length > 50) return ElMessage.warning('用户名最多 50 个字符');
        if (!f.password) return ElMessage.warning('请输入密码');
        if (f.password.length < 6) return ElMessage.warning('密码至少 6 位');
        if (f.password.length > 64) return ElMessage.warning('密码最多 64 位');
        const hasQ = !!(f.sec_question || '').trim();
        const hasA = !!(f.sec_answer || '').trim();
        if (hasQ !== hasA) return ElMessage.warning('密保问题与答案需同时填写（或都留空）');
        if (f.role === 'teacher' && !(f.invite_code || '').trim()) return ElMessage.warning('教师注册需要填写邀请码，请向管理员获取');
        f.username = u;
        doRegister();
      }

      // 忘记密码两步流程
      const fp = ref({ step: 1, username: '', question: '', answer: '', new_password: '', confirm: '' });
      function fpReset() {                 // 每次进入/完成后重置，避免残留上一人的用户名与问题
        fp.value = { step: 1, username: '', question: '', answer: '', new_password: '', confirm: '' };
      }
      function openForgot() { fpReset(); mode.value = 'forgot'; }
      async function fpNext() {
        if (fpLoading.value) return;               // 防连点重复请求
        if (!fp.value.username.trim()) return ElMessage.warning('请输入用户名');
        fpLoading.value = true;
        try {
          const r = await A.secQuestion(fp.value.username.trim());
          if (r.detail) return ElMessage.error(r.detail);
          fp.value.question = r.question;
          fp.value.step = 2;
        } catch (e) {
          ElMessage.error('网络异常，请检查连接后重试');
        } finally { fpLoading.value = false; }
      }
      async function fpSubmit() {
        if (fpLoading.value) return;
        const f = fp.value;
        if (!f.answer.trim()) return ElMessage.warning('请输入密保答案');
        if (f.new_password.length < 6) return ElMessage.warning('新密码至少 6 位');
        if (f.new_password !== f.confirm) return ElMessage.warning('两次输入的新密码不一致');
        fpLoading.value = true;
        try {
          const r = await A.forgotPassword({ username: f.username.trim(), answer: f.answer, new_password: f.new_password });
          if (r.detail) return ElMessage.error(r.detail);
          ElMessage.success(r.message);
          fpReset();
          mode.value = 'login';
        } catch (e) {
          ElMessage.error('网络异常，请检查连接后重试');
        } finally { fpLoading.value = false; }
      }

      return { s: state, mode, doLogin, doRegister, submitRegister, fpLoading, openForgot,
               fp, fpNext, fpSubmit, SEC_QUESTIONS };
    },
    template: `
    <div class="login-screen">
      <img class="login-bg" src="/assets/bg.png" alt="">
      <div class="login-panel">
        <div class="login-brand">
          <div class="logo">📚</div>
          <h1>个性化学习资源推荐系统</h1>
          <div class="sub">Web 数据挖掘课程原型系统<br/>基于协同过滤的校园学习资源 Top-N 推荐</div>
          <ul>
            <li><span class="ic">🎯</span>协同过滤 + SVD，Top-N 个性化推荐</li>
            <li><span class="ic">🔥</span>兴趣标签冷启动 + 热门资源兜底</li>
            <li><span class="ic">📊</span>浏览 / 收藏 / 评分行为采集与画像</li>
            <li><span class="ic">📈</span>离线实验评估，效果可视化监控</li>
          </ul>
          <div class="foot">Personalized Learning Resource Recommendation System</div>
        </div>
        <div class="login-main">
          <el-tabs v-model="mode" stretch>
            <el-tab-pane label="账号登录" name="login">
              <div style="height:16px"></div>
              <el-form @submit.prevent>
                <el-form-item>
                  <el-input v-model="s.loginForm.username" placeholder="用户名" size="large" clearable>
                    <template #prefix>👤</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="s.loginForm.password" placeholder="密码" type="password" size="large"
                            show-password @keyup.enter="doLogin">
                    <template #prefix>🔒</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <div style="width:100%;display:flex;justify-content:space-between;align-items:center">
                    <el-checkbox v-model="s.loginForm.remember">记住我 7 天</el-checkbox>
                    <el-link type="primary" :underline="false" style="font-size:12px"
                             @click="openForgot">忘记密码？</el-link>
                  </div>
                </el-form-item>
                <el-button class="login-btn" type="primary" :loading="s.loginLoading" @click="doLogin">登 录</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="注册新账号" name="register">
              <div style="height:16px"></div>
              <el-form @submit.prevent>
                <el-form-item>
                  <div style="width:100%;display:flex;align-items:center;gap:12px">
                    <span style="font-size:13px;color:#666;flex:none">注册身份：</span>
                    <el-radio-group v-model="s.regForm.role" size="small">
                      <el-radio-button value="student">🎓 学生</el-radio-button>
                      <el-radio-button value="teacher">👨‍🏫 教师</el-radio-button>
                    </el-radio-group>
                  </div>
                </el-form-item>
                <el-form-item v-if="s.regForm.role === 'teacher'">
                  <el-input v-model="s.regForm.invite_code" placeholder="教师邀请码（向管理员获取，一次性使用）" size="large" clearable>
                    <template #prefix>🎟️</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="s.regForm.username" placeholder="用户名（2~50 字符）" size="large" clearable>
                    <template #prefix>👤</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="s.regForm.password" placeholder="密码（至少 6 位）" type="password" size="large" show-password>
                    <template #prefix>🔒</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="s.regForm.nickname" placeholder="昵称（选填）" size="large" clearable>
                    <template #prefix>🏷️</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <div style="width:100%;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
                    <el-radio-group v-model="s.regForm.gender" size="small">
                      <el-radio-button value="男">👨 男</el-radio-button>
                      <el-radio-button value="女">👩 女</el-radio-button>
                      <el-radio-button value="保密">🙈 保密</el-radio-button>
                    </el-radio-group>
                    <el-input v-model="s.regForm.grade" placeholder="年级（如 2024级）" style="width:150px" clearable></el-input>
                    <el-input v-model="s.regForm.college" placeholder="学院（选填）" style="width:160px" clearable></el-input>
                  </div>
                </el-form-item>
                <el-form-item>
                  <div style="width:100%">
                    <div style="font-size:13px;color:#666;margin-bottom:6px">
                      🎯 选择感兴趣的类别（<b style="color:#409eff">兴趣冷启动</b>：注册即可获得个性化推荐）
                    </div>
                    <el-checkbox-group v-model="s.regForm.interests">
                      <el-checkbox v-for="c in s.categories" :key="c" :value="c">{{ c }}</el-checkbox>
                    </el-checkbox-group>
                  </div>
                </el-form-item>
                <el-form-item>
                  <div style="width:100%;display:flex;gap:10px;align-items:center">
                    <span style="font-size:13px;color:#666;flex:none">🔒 密保：</span>
                    <el-select v-model="s.regForm.sec_question" placeholder="选择密保问题（用于找回密码）"
                               style="flex:1" clearable>
                      <el-option v-for="q in SEC_QUESTIONS" :key="q" :label="q" :value="q"></el-option>
                    </el-select>
                    <el-input v-model="s.regForm.sec_answer" placeholder="答案" style="width:130px" clearable></el-input>
                  </div>
                </el-form-item>
                <el-button class="login-btn" type="primary" :loading="s.loginLoading" @click="submitRegister">注 册</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="忘记密码" name="forgot">
              <div style="height:16px"></div>
              <el-form @submit.prevent v-if="fp.step === 1">
                <div class="hint" style="color:#98a5bd;font-size:13px;margin-bottom:16px">
                  输入注册时的用户名，系统将展示你的密保问题
                </div>
                <el-form-item>
                  <el-input v-model="fp.username" placeholder="用户名" size="large" clearable>
                    <template #prefix>👤</template>
                  </el-input>
                </el-form-item>
                <el-button class="login-btn" type="primary" :loading="fpLoading" @click="fpNext">下一步：回答密保问题</el-button>
              </el-form>

              <el-form @submit.prevent v-else>
                <div class="hint" style="color:#98a5bd;font-size:13px;margin-bottom:16px">
                  密保问题：<b style="color:#409eff">{{ fp.question }}</b>
                </div>
                <el-form-item>
                  <el-input v-model="fp.answer" placeholder="密保答案" size="large" clearable>
                    <template #prefix>💬</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="fp.new_password" placeholder="新密码（至少 6 位）" type="password" size="large" show-password>
                    <template #prefix>🔒</template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="fp.confirm" placeholder="确认新密码" type="password" size="large" show-password>
                    <template #prefix>✅</template>
                  </el-input>
                </el-form-item>
                <el-button class="login-btn" type="primary" :loading="fpLoading" @click="fpSubmit">重置密码</el-button>
              </el-form>
              <div style="text-align:center;margin-top:14px">
                <el-link type="primary" :underline="false" style="font-size:12px"
                         @click="mode='login'; fp.step=1">返回登录</el-link>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>`
  };
})();
