const ProjectDetailView = {
  template: `
  <div>
    <a href="javascript:;" @click="$router.go('/projects')" class="muted">← 返回项目列表</a>
    <h2 style="margin:12px 0 16px">{{ p.name }} <span class="badge gray">{{ p.code }}</span> <span v-html="StatusBadge(p.status)"></span></h2>
    <div class="card">
      <div class="flex wrap">
        <div class="stat" style="flex:1"><div class="num">¥{{ fmt(p.budget) }}</div><div class="label">预算金额</div></div>
        <div class="stat" style="flex:1"><div class="num">{{ p.sections }}</div><div class="label">标段数</div></div>
        <div class="stat" style="flex:1"><div class="num">{{ p.category }}</div><div class="label">项目类别</div></div>
      </div>
      <p class="muted mt">{{ p.description }}</p>
    </div>
    <div class="card">
      <h2>标段管理</h2>
      <div class="toolbar">
        <div class="flex" style="flex:1">
          <input v-model="form.code" placeholder="标段编号，如 BD-2026-001" style="flex:1">
          <input v-model="form.name" placeholder="标段名称" style="flex:1">
          <select v-model="form.method" style="width:150px">
            <option value="comprehensive">综合评分法</option>
            <option value="lowest_price">最低价法</option>
          </select>
          <input v-model.number="form.notice_days" type="number" style="width:90px" title="公示天数">
          <button class="btn primary" @click="createSection">新建标段</button>
        </div>
      </div>
      <table>
        <thead><tr><th>编号</th><th>名称</th><th>评标方法</th><th>状态</th><th>保证金比例</th><th></th></tr></thead>
        <tbody>
          <tr v-for="s in sections" :key="s.id">
            <td>{{ s.code }}</td><td>{{ s.name }}</td>
            <td>{{ s.method === 'comprehensive' ? '综合评分法' : '最低价法' }}</td>
            <td v-html="StatusBadge(s.status)"></td>
            <td>{{ (s.deposit_ratio * 100).toFixed(1) }}%</td>
            <td><a href="javascript:;" @click="$router.go('/sections/' + s.id)">管理标段</a></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!sections.length" class="muted">暂无标段</p>
    </div>
  </div>`,
  props: { route: Object },
  data() { return { p: {}, sections: [], form: { code: "", name: "", method: "comprehensive", notice_days: 3 } }; },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      const data = await Api.get(`/api/projects/${this.route.params.id}`);
      this.p = data; this.sections = data.sections;
    },
    async createSection() {
      try {
        await Api.post(`/api/projects/${this.route.params.id}/sections`, this.form);
        this.form = { code: "", name: "", method: "comprehensive", notice_days: 3 };
        await this.load();
      } catch (e) { alert(e.message); }
    },
    fmt(n) { return Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2 }); },
  },
};
