const ProjectsView = {
  template: `
  <div>
    <h2 style="margin-bottom:16px">招标项目管理</h2>
    <div class="card">
      <h2>新建招标项目</h2>
      <div class="form-row"><label>项目编号</label><input v-model="form.code" placeholder="如 ZB-2026-001"></div>
      <div class="form-row"><label>项目名称</label><input v-model="form.name"></div>
      <div class="form-row"><label>类别</label>
        <select v-model="form.category"><option>货物</option><option>服务</option><option>工程</option></select>
      </div>
      <div class="form-row"><label>预算金额</label><input v-model.number="form.budget" type="number" step="0.01"></div>
      <div class="form-row"><label>说明</label><textarea v-model="form.description" rows="2"></textarea></div>
      <button class="btn primary" @click="create">创建项目</button>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>编号</th><th>名称</th><th>类别</th><th>预算</th><th>标段</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in projects" :key="p.id">
            <td>{{ p.code }}</td><td>{{ p.name }}</td><td>{{ p.category }}</td>
            <td>¥{{ fmt(p.budget) }}</td><td>{{ p.sections }}</td>
            <td v-html="StatusBadge(p.status)"></td>
            <td><a href="javascript:;" @click="$router.go('/projects/' + p.id)">详情</a></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!projects.length" class="muted">暂无项目</p>
    </div>
  </div>`,
  data() { return { projects: [], form: { code: "", name: "", category: "货物", budget: 0, description: "" } }; },
  async mounted() { await this.load(); },
  methods: {
    async load() { this.projects = await Api.get("/api/projects"); },
    async create() {
      try {
        await Api.post("/api/projects", this.form);
        this.form = { code: "", name: "", category: "货物", budget: 0, description: "" };
        await this.load();
      } catch (e) { alert(e.message); }
    },
    fmt(n) { return Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2 }); },
  },
};
