const LoginView = {
  template: `
  <div class="login-wrap">
    <div class="card">
      <h1>招投标管理系统</h1>
      <div v-if="error" class="alert err">{{ error }}</div>
      <div class="form-row"><label>用户名</label><input v-model="username" placeholder="请输入用户名"></div>
      <div class="form-row"><label>密码</label><input v-model="password" type="password" placeholder="请输入密码" @keyup.enter="doLogin"></div>
      <button class="btn primary login-btn" :disabled="loading" @click="doLogin">{{ loading ? '登录中...' : '登 录' }}</button>
      <p class="muted mt" style="text-align:center">admin / operator / bidder1 / judge1，密码均为 123456</p>
    </div>
  </div>`,
  data() { return { username: "", password: "", error: "", loading: false }; },
  methods: {
    async doLogin() {
      this.loading = true; this.error = "";
      try {
        const res = await Api.post("/api/auth/login", { username: this.username, password: this.password });
        this.$emit("login", res.user);
      } catch (e) { this.error = e.message; }
      finally { this.loading = false; }
    },
  },
};
