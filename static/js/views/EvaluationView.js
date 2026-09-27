const EvaluationView = {
  template: `
  <div>
    <a href="javascript:;" @click="$router.go('/sections/' + sectionId)" class="muted">← 返回标段</a>
    <h2 style="margin:12px 0 16px">评标管理</h2>

    <div class="card">
      <h2>评标规则</h2>
      <div class="form-row"><label>评标方法</label>
        <select v-model="rule.method">
          <option value="comprehensive">综合评分法</option>
          <option value="lowest_price">最低价法</option>
        </select>
      </div>
      <div class="form-row"><label>价格权重</label><input v-model.number="rule.price_weight" type="number" step="0.05"></div>
      <div class="form-row"><label>价格满分</label><input v-model.number="rule.price_full_score" type="number"></div>
      <div class="form-row"><label>异常低价阈值</label><input v-model.number="rule.abnormal_price_ratio" type="number" step="0.05"></div>
      <div class="form-row"><label>去掉最高最低分</label>
        <select v-model.number="rule.drop_highest_lowest"><option :value="1">是</option><option :value="0">否</option></select>
      </div>
      <button class="btn primary" @click="saveRule">保存规则</button>
    </div>

    <div class="card">
      <h2>评分项</h2>
      <div class="flex" style="margin-bottom:10px">
        <input v-model="itemForm.name" placeholder="评分项名称" style="flex:1">
        <select v-model="itemForm.category" style="width:130px"><option value="tech">技术</option><option value="business">商务</option></select>
        <input v-model.number="itemForm.weight" type="number" step="0.05" style="width:90px" title="权重">
        <input v-model.number="itemForm.full_score" type="number" style="width:90px" title="满分">
        <button class="btn" @click="addItem">添加</button>
      </div>
      <table>
        <thead><tr><th>名称</th><th>类别</th><th>权重</th><th>满分</th></tr></thead>
        <tbody><tr v-for="i in items" :key="i.id"><td>{{ i.name }}</td><td>{{ i.category }}</td><td>{{ i.weight }}</td><td>{{ i.full_score }}</td></tr></tbody>
      </table>
    </div>

    <div class="card" v-if="judges.length && rule.method === 'comprehensive'">
      <h2>评委打分</h2>
      <div class="form-row"><label>投标文件</label>
        <select v-model="scoreForm.bid_document_id">
          <option v-for="b in bids" :key="b.id" :value="b.id">{{ b.company }}（¥{{ b.price }}）</option>
        </select>
      </div>
      <div class="form-row" v-for="i in items" :key="i.id">
        <label>{{ i.name }}（满分 {{ i.full_score }}）</label>
        <input v-model="scoreForm.scores[String(i.id)]" type="number" :max="i.full_score">
      </div>
      <button class="btn primary" @click="submitScores">提交打分</button>
    </div>

    <div class="card">
      <h2>开标</h2>
      <button class="btn primary" @click="openEval" :disabled="opening">{{ opening ? '开标中...' : '开始评标 / 开标' }}</button>
      <div v-if="result" class="mt">
        <div class="alert" :class="result.abnormal_prices.length ? 'err' : 'ok'">
          异常低价报价数：{{ result.abnormal_prices.length }}
          <span v-for="p in result.abnormal_prices" :key="p">｜¥{{ p }}</span>
        </div>
        <div v-if="result.pending_clarification && result.pending_clarification.length" class="alert err">
          {{ result.message || '以下投标报价异常偏低，需完成澄清或排除处理后方可定标。' }}
        </div>
        <div v-if="result.pending_clarification && result.pending_clarification.length" class="card" style="background:#fff8f0">
          <h2>异常低价澄清</h2>
          <div class="form-row"><label>处理说明</label><input v-model="clarifyReason" placeholder="澄清/排除理由（记入审计日志）"></div>
          <table>
            <thead><tr><th>公司</th><th>报价</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="c in result.pending_clarification" :key="c.bid_document_id">
                <td>{{ c.company }}</td><td>¥{{ c.price }}</td>
                <td>
                  <button class="btn small" @click="resolveClarify(c.bid_document_id, 'accept')">澄清通过</button>
                  <button class="btn small danger" @click="resolveClarify(c.bid_document_id, 'exclude')">排除并退保证金</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <table>
          <thead><tr><th>排名</th><th>公司</th><th>报价</th><th>价格分</th><th>总分</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="(r, idx) in result.ranked" :key="r.bid_document_id">
              <td>{{ idx + 1 }}</td><td>{{ r.company }}</td><td>¥{{ r.price }}</td>
              <td>{{ r.price_score }}</td><td><b>{{ r.total }}</b></td>
              <td>
                <span v-if="r.abnormal" class="badge red">异常低价</span>
                <span v-else-if="r.status" v-html="StatusBadge(r.status)"></span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="result.winner_bid_id" class="mt">中标候选人：<b>{{ result.winner_company }}</b>，报价 ¥{{ result.winner_price }}，公示至 {{ fmtDate(result.publish_end) }}</p>
        <p v-else class="mt muted">异常低价澄清/排除处理完成前，暂不产生中标候选人，标段保持「评标中」状态。</p>
      </div>
    </div>
  </div>`,
  props: { route: Object },
  data() {
    return {
      sectionId: null, rule: { method: "comprehensive", price_weight: 0.4, price_full_score: 100, abnormal_price_ratio: 0.6, drop_highest_lowest: 1 },
      items: [], judges: [], bids: [], result: null, opening: false, clarifyReason: "",
      itemForm: { name: "", category: "tech", weight: 0.1, full_score: 10 },
      scoreForm: { bid_document_id: null, scores: {} },
    };
  },
  async mounted() {
    this.sectionId = this.route.params.id;
    const res = await Api.get(`/api/sections/${this.sectionId}/evaluation`);
    this.rule = res.rule; this.items = res.items; this.judges = res.judges;
    this.bids = await Api.get(`/api/sections/${this.sectionId}/bids`);
  },
  methods: {
    async saveRule() {
      try { await Api.post(`/api/sections/${this.sectionId}/evaluation/rule`, this.rule); alert("规则已保存"); }
      catch (e) { alert(e.message); }
    },
    async addItem() {
      if (!this.itemForm.name) return alert("请输入评分项名称");
      try { await Api.post(`/api/sections/${this.sectionId}/evaluation/items`, this.itemForm); this.itemForm = { name: "", category: "tech", weight: 0.1, full_score: 10 }; await this.refresh(); }
      catch (e) { alert(e.message); }
    },
    async submitScores() {
      if (!this.scoreForm.bid_document_id) return alert("请选择投标文件");
      const payload = { bid_document_id: this.scoreForm.bid_document_id, scores: { ...this.scoreForm.scores } };
      try { await Api.post(`/api/sections/${this.sectionId}/evaluation/scores`, payload); alert("打分已提交"); }
      catch (e) { alert(e.message); }
    },
    async openEval() {
      this.opening = true;
      try { this.result = await Api.post(`/api/sections/${this.sectionId}/evaluation/open`); }
      catch (e) { alert(e.message); }
      finally { this.opening = false; }
    },
    async resolveClarify(bidId, action) {
      const label = action === "accept" ? "澄清通过" : "排除该投标并退还保证金";
      if (!confirm(`确认对该异常低价投标执行「${label}」？`)) return;
      try {
        const res = await Api.post(`/api/sections/${this.sectionId}/evaluation/clarify`, {
          bid_document_id: bidId, action, reason: this.clarifyReason,
        });
        this.result.pending_clarification = this.result.pending_clarification.filter(c => c.bid_document_id !== bidId);
        const row = this.result.ranked.find(r => r.bid_document_id === bidId);
        if (row) { row.status = res.status; row.abnormal = false; }
        alert(res.remaining_clarifications > 0
          ? `已处理，剩余待澄清 ${res.remaining_clarifications} 笔`
          : "全部澄清处理完毕，请重新开标以完成定标");
      } catch (e) { alert(e.message); }
    },
    async refresh() { const res = await Api.get(`/api/sections/${this.sectionId}/evaluation`); this.items = res.items; this.judges = res.judges; },
    fmtDate(d) { return d ? String(d).replace("T", " ").slice(0, 16) : "-"; },
  },
};
