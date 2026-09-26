const SectionView = {
  template: `
  <div>
    <a href="javascript:;" @click="$router.go('/projects/' + s.project_id)" class="muted">← 返回项目</a>
    <h2 style="margin:12px 0 16px">{{ s.name }} <span class="badge gray">{{ s.code }}</span> <span v-html="StatusBadge(s.status)"></span></h2>

    <div class="card">
      <h2>标段信息与状态流转</h2>
      <div class="flex wrap">
        <span class="chip">评标方法：{{ s.method === 'comprehensive' ? '综合评分法' : '最低价法' }}</span>
        <span class="chip">保证金比例：{{ (s.deposit_ratio * 100).toFixed(1) }}%</span>
        <span class="chip">公示天数：{{ s.notice_days }} 天</span>
      </div>
      <div class="toolbar mt">
        <button class="btn primary" @click="transition('announced')">发布招标公告</button>
        <button class="btn" @click="transition('evaluating')">进入评标</button>
        <button class="btn" @click="transition('failed')">标记流标</button>
        <button class="btn danger" @click="transition('closed')">关闭标段</button>
        <a class="btn" :href="'#/sections/' + s.id + '/evaluation'">评标管理</a>
        <a class="btn" :href="'#/sections/' + s.id + '/escrow'">保证金管理</a>
      </div>
      <div class="toolbar mt">
        <input v-model="ann.title" placeholder="公告标题" style="max-width:280px">
        <input v-model="ann.content" placeholder="公告内容" style="flex:1">
        <button class="btn" @click="postAnnouncement">发布公告</button>
      </div>
      <div class="mt" v-if="statusLogs.length">
        <b class="muted">状态轨迹：</b>
        <span class="muted" v-for="(l, i) in statusLogs" :key="i">
          {{ i > 0 ? ' → ' : '' }}{{ l.from || '—' }}<b>→</b>{{ l.to }}
        </span>
      </div>
    </div>

    <div class="card" v-if="isBidder">
      <h2>提交投标文件</h2>
      <div class="alert err" v-if="!canBid">当前标段状态不允许投标</div>
      <div class="form-row"><label>投标报价</label><input v-model.number="bidForm.price" type="number" step="0.01"></div>
      <div class="form-row"><label>营业执照有效期</label><input v-model="bidForm.license_expiry" placeholder="YYYY-MM-DD"></div>
      <div class="form-row"><label>技术方案</label><textarea v-model="bidForm.tech_material" rows="2"></textarea></div>
      <button class="btn primary" :disabled="!canBid" @click="submitBid">提交投标</button>
      <div v-if="lastCompliance" class="alert mt" :class="lastCompliance.passed ? 'ok' : 'err'">
        合规校验：{{ lastCompliance.passed ? '通过' : '未通过' }}
        <span v-for="e in lastCompliance.errors" :key="e">｜{{ e }}</span>
      </div>
    </div>

    <div class="card">
      <h2>投标列表（{{ bids.length }}）</h2>
      <table>
        <thead><tr><th>公司</th><th>报价</th><th>执照有效期</th><th>合规状态</th><th>投标状态</th><th></th></tr></thead>
        <tbody>
          <tr v-for="b in bids" :key="b.id">
            <td>{{ b.company }}</td><td>¥{{ fmt(b.price) }}</td><td>{{ b.license_expiry }}</td>
            <td v-html="b.compliance.passed ? StatusBadge('qualified') : StatusBadge('disqualified')"></td>
            <td v-html="StatusBadge(b.status)"></td>
            <td><button class="btn small" @click="recheck(b.id)">重新校验</button></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!bids.length" class="muted">暂无投标</p>
    </div>

    <div class="card" v-if="s.winner">
      <h2>中标公示</h2>
      <div class="flex wrap">
        <span class="chip">中标价：¥{{ fmt(s.winner.win_price) }}</span>
        <span class="chip">公示期：{{ fmtDate(s.winner.publish_start) }} ~ {{ fmtDate(s.winner.publish_end) }}</span>
        <span v-html="StatusBadge(s.winner.status)"></span>
      </div>
      <button class="btn primary mt" @click="confirmWinner" :disabled="s.winner.status !== 'pending'">确认中标（公示到期）</button>
    </div>
  </div>`,
  props: { route: Object },
  data() {
    return {
      s: {}, bids: [], statusLogs: [], user: null, lastCompliance: null,
      ann: { title: "", content: "" },
      bidForm: { price: null, license_expiry: "", tech_material: "" },
    };
  },
  computed: {
    isBidder() { return this.user && this.user.role === "bidder"; },
    canBid() { return ["announced", "bidding"].includes(this.s.status); },
  },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      const res = await Api.get(`/api/sections/${this.route.params.id}`);
      this.s = res; this.bids = res.bids; this.statusLogs = res.status_logs;
      try { this.user = (await Api.get("/api/auth/me")); } catch (e) { /* ignore */ }
    },
    async transition(to) {
      const ok = confirm(`确认将标段状态流转为「${to}」？`);
      if (!ok) return;
      try { await Api.post(`/api/sections/${this.s.id}/transition`, { to_status: to, remark: "页面操作" }); await this.load(); }
      catch (e) { alert(e.message); }
    },
    async postAnnouncement() {
      if (!this.ann.title) return alert("请输入公告标题");
      try { await Api.post(`/api/sections/${this.s.id}/announcements`, this.ann); this.ann = { title: "", content: "" }; await this.load(); }
      catch (e) { alert(e.message); }
    },
    async submitBid() {
      if (this.bidForm.price == null) return alert("请输入报价");
      try {
        const res = await Api.post(`/api/sections/${this.s.id}/bids`, this.bidForm);
        this.lastCompliance = res.compliance;
        this.bidForm = { price: null, license_expiry: "", tech_material: "" };
        await this.load();
      } catch (e) { alert(e.message); }
    },
    async recheck(id) {
      try { await Api.post(`/api/bids/${id}/recheck`); await this.load(); } catch (e) { alert(e.message); }
    },
    async confirmWinner() {
      try {
        const res = await Api.post(`/api/winners/${this.s.winner.id}/confirm`);
        alert(res.ok ? "中标已确认" : res.message);
        await this.load();
      } catch (e) { alert(e.message); }
    },
    fmt(n) { return Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2 }); },
    fmtDate(d) { return d ? String(d).replace("T", " ").slice(0, 16) : "-"; },
  },
};
