const EscrowView = {
  template: `
  <div>
    <a href="javascript:;" @click="$router.go('/sections/' + sectionId)" class="muted">← 返回标段</a>
    <h2 style="margin:12px 0 16px">投标保证金管理</h2>
    <div class="card">
      <table>
        <thead><tr><th>ID</th><th>投标文件</th><th>金额</th><th>状态</th><th>缴纳时间</th><th>退还时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in accounts" :key="a.id">
            <td>{{ a.id }}</td><td>#{{ a.bid_document_id }}</td>
            <td>¥{{ fmt(a.amount) }}</td>
            <td v-html="StatusBadge(a.status)"></td>
            <td>{{ fmtDate(a.paid_at) }}</td><td>{{ fmtDate(a.returned_at) }}</td>
            <td>
              <button class="btn small" @click="pay(a.id)" v-if="a.status === 'unpaid'">缴纳</button>
              <button class="btn small" @click="ret(a.id)" v-if="a.status === 'paid'">退还</button>
              <button class="btn small danger" @click="forfeit(a.id)" v-if="a.status === 'paid'">没收</button>
              <button class="btn small" @click="showTx(a.id)">流水</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!accounts.length" class="muted">暂无保证金账户</p>
      <div v-if="txs.length" class="mt">
        <b>账户 #{{ currentAccount }} 流水：</b>
        <table class="mt"><thead><tr><th>类型</th><th>金额</th><th>余额</th><th>说明</th><th>时间</th></tr></thead>
        <tbody><tr v-for="(t, i) in txs" :key="i"><td>{{ t.tx_type }}</td><td>¥{{ t.amount }}</td><td>¥{{ t.balance_after }}</td><td>{{ t.remark }}</td><td>{{ fmtDate(t.created_at) }}</td></tr></tbody></table>
      </div>
    </div>
  </div>`,
  props: { route: Object },
  data() { return { sectionId: null, accounts: [], txs: [], currentAccount: null }; },
  async mounted() {
    this.sectionId = this.route.params.id;
    this.accounts = await Api.get(`/api/sections/${this.sectionId}/escrow`);
  },
  methods: {
    async pay(id) { try { await Api.post(`/api/escrow/${id}/pay`); await this.reload(); } catch (e) { alert(e.message); } },
    async ret(id) { try { await Api.post(`/api/escrow/${id}/return`); await this.reload(); } catch (e) { alert(e.message); } },
    async forfeit(id) { try { await Api.post(`/api/escrow/${id}/forfeit`); await this.reload(); } catch (e) { alert(e.message); } },
    async showTx(id) { this.currentAccount = id; this.txs = await Api.get(`/api/escrow/${id}/transactions`); },
    async reload() { this.accounts = await Api.get(`/api/sections/${this.sectionId}/escrow`); },
    fmt(n) { return Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2 }); },
    fmtDate(d) { return d ? String(d).replace("T", " ").slice(0, 16) : "-"; },
  },
};
