const parseHash = () => {
  const m = location.hash.match(/^#\/([a-z]+)(?:\/(\d+)(?:\/([a-z]+))?)?/);
  const path = m ? m[1] : "dashboard";
  const id = m && m[2] ? Number(m[2]) : null;
  const sub = (m && m[3]) || "";
  return { path, params: { id, sub } };
};

const AppShell = {
  template: `
  <div v-if="!user">
    <component :is="'login-view'" @login="onLogin"></component>
  </div>
  <div v-else>
    <nav class="nav">
      <span class="brand">招投标管理系统</span>
      <a href="#/dashboard" :class="{ active: route.path === 'dashboard' }">仪表盘</a>
      <a href="#/projects" :class="{ active: route.path === 'projects' }">招标项目</a>
      <a href="#/audit" :class="{ active: route.path === 'audit' }">审计日志</a>
      <span class="spacer"></span>
      <span class="user">{{ user.display_name }}（{{ roleLabel }}）</span>
      <a href="javascript:;" @click="logout">退出</a>
    </nav>
    <div class="container">
      <component :is="currentView" :route="route" :key="route.path + (route.params.id || '')"></component>
    </div>
  </div>`,
  data() {
    return {
      user: null,
      route: { path: "dashboard", params: {} },
    };
  },
  computed: {
    currentView() {
      const { path, params } = this.route;
      if (path === "login") return "login-view";
      if (path === "projects" && params.id) return "project-detail-view";
      if (path === "sections" && params.id && params.sub === "evaluation") return "evaluation-view";
      if (path === "sections" && params.id && params.sub === "escrow") return "escrow-view";
      if (path === "sections" && params.id) return "section-view";
      if (path === "audit") return "audit-view";
      if (path === "dashboard") return "dashboard-view";
      return "projects-view";
    },
    roleLabel() {
      const m = { admin: "管理员", operator: "招标经办", bidder: "投标人", judge: "评委" };
      return m[this.user.role] || this.user.role;
    },
  },
  created() {
    this.syncRoute();
    window.addEventListener("hashchange", this.syncRoute);
  },
  methods: {
    syncRoute() {
      const parsed = parseHash();
      this.route = parsed;
      this.checkAuth();
    },
    async checkAuth() {
      try {
        const me = await Api.get("/api/auth/me");
        this.user = me;
      } catch (e) {
        this.user = null;
        if (!location.hash.startsWith("#/login")) location.hash = "#/login";
      }
    },
    onLogin(user) {
      this.user = user;
      location.hash = "#/dashboard";
    },
    async logout() {
      try { await Api.post("/api/auth/logout"); } catch (e) { /* ignore */ }
      this.user = null;
      location.hash = "#/login";
    },
  },
};

const app = Vue.createApp(AppShell);
app.component("login-view", LoginView);
app.component("dashboard-view", DashboardView);
app.component("projects-view", ProjectsView);
app.component("project-detail-view", ProjectDetailView);
app.component("section-view", SectionView);
app.component("evaluation-view", EvaluationView);
app.component("escrow-view", EscrowView);
app.component("audit-view", AuditView);
app.mount("#app");
