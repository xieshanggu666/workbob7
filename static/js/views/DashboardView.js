const DashboardView = {
  template: `
  <div>
    <h2 style="margin-bottom:16px">数据总览</h2>
    <div class="grid cols-4">
      <div class="stat"><div class="num">{{ s.total_projects }}</div><div class="label">招标项目</div></div>
      <div class="stat"><div class="num">{{ s.total_sections }}</div><div class="label">标段数</div></div>
      <div class="stat"><div class="num">{{ s.total_bids }}</div><div class="label">投标文件</div></div>
      <div class="stat"><div class="num">¥{{ fmt(s.paid_escrow) }}</div><div class="label">已缴保证金</div></div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card">
        <h2>项目状态分布</h2>
        <div class="chips">
          <span v-for="(v, k) in s.projects_by_status" :key="k" class="chip">
            {{ label(k) }}：<b>{{ v }}</b>
          </span>
        </div>
      </div>
      <div class="card">
        <h2>标段状态分布</h2>
        <div class="chips">
          <span v-for="(v, k) in s.sections_by_status" :key="k" class="chip">
            {{ label(k) }}：<b>{{ v }}</b>
          </span>
        </div>
      </div>
    </div>
  </div>`,
  data() { return { s: { total_projects: 0, total_sections: 0, total_bids: 0, paid_escrow: 0, projects_by_status: {}, sections_by_status: {} } }; },
  async mounted() { this.s = await Api.get("/api/dashboard"); },
  methods: {
    fmt(n) { return Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2 }); },
    label(k) {
      const m = { draft: "草稿", published: "已发布", bidding: "招标中", announced: "公告中", evaluating: "评标中", awarded: "已定标", failed: "流标", closed: "已关闭" };
      return m[k] || k;
    },
  },
};
