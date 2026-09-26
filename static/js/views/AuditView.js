const AuditView = {
  template: `
  <div>
    <h2 style="margin-bottom:16px">审计日志</h2>
    <div class="card">
      <table>
        <thead><tr><th>时间</th><th>操作</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="(l, i) in logs" :key="i">
            <td>{{ fmtDate(l.created_at) }}</td><td><span class="badge blue">{{ l.action }}</span></td><td>{{ l.detail }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!logs.length" class="muted">暂无日志</p>
    </div>
  </div>`,
  data() { return { logs: [] }; },
  async mounted() { this.logs = await Api.get("/api/audit"); },
  methods: { fmtDate(d) { return d ? String(d).replace("T", " ").slice(0, 19) : "-"; } },
};
