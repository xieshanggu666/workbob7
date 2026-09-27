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
      <h2>异常低价澄清</h2>
      <p v-if="!clarifications.length" class="muted">暂无异常低价澄清记录</p>
      <table v-else>
        <thead><tr><th>公司</th><th>报价</th><th>阈值</th><th>状态</th><th>截止时间</th><th>澄清说明</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="c in clarifications" :key="c.id">
            <td>{{ companyOfBid(c.bid_document_id) }}</td>
            <td>¥{{ c.suspected_price }}</td>
            <td>¥{{ c.threshold_price }}</td>
            <td v-html="StatusBadge(c.status)"></td>
            <td>{{ fmtDate(c.deadline) }}</td>
            <td>{{ c.response_content || c.review_remark || '-' }}</td>
            <td>
              <template v-if="isBidder && c.bidder_id === user.id && c.status === 'pending'">
                <textarea v-model="responses[c.id]" rows="2" placeholder="说明成本、材料、履约保障等"></textarea>
                <button class="btn small primary" @click="submitClarification(c)">提交澄清</button>
              </template>
              <template v-if="canManage && ['pending', 'responded'].includes(c.status)">
                <button class="btn small" @click="reviewClarification(c, 'accepted')">澄清成立</button>
                <button class="btn small danger" @click="reviewClarification(c, 'excluded')">排除报价</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>开标</h2>
      <button class="btn primary" @click="openEval" :disabled="opening">{{ opening ? '开标中...' : '开始评标 / 开标' }}</button>
      <div v-if="result" class="mt">
        <div class="alert" :class="result.needs_clarification || result.abnormal_prices.length ? 'err' : 'ok'">
          <template v-if="result.needs_clarification">
            存在 {{ result.active_clarifications.length }} 份异常低价待澄清；标段保持评标中，不生成中标公示。
          </template>
          <template v-else-if="result.failed">异常低价排除后无有效投标，标段已流标。</template>
          <template v-else>异常低价均已处理，可以进入定标公示。</template>
        </div>
        <table>
          <thead><tr><th>排名</th><th>公司</th><th>报价</th><th>状态</th><th>价格分</th><th>总分</th></tr></thead>
          <tbody>
            <tr v-for="(r, idx) in result.ranked" :key="r.bid_document_id">
              <td>{{ idx + 1 }}</td><td>{{ r.company }}</td><td>¥{{ r.price }}</td>
              <td v-if="r.status" v-html="StatusBadge(r.status)"></td><td v-else>-</td>
              <td>{{ r.price_score }}</td><td><b>{{ r.total }}</b></td>
            </tr>
          </tbody>
        </table>
        <p v-if="result.awarded" class="mt">中标候选人：<b>{{ result.winner_company }}</b>，报价 ¥{{ result.winner_price }}，公示至 {{ fmtDate(result.publish_end) }}</p>
        <p v-else-if="result.needs_clarification" class="mt">请投标人完成澄清并由经办/管理员审核，异常报价不会进入当前排名和后续定标链路。</p>
      </div>
    </div>
  </div>`,
  props: { route: Object },
  data() {
    return {
      sectionId: null, rule: { method: "comprehensive", price_weight: 0.4, price_full_score: 100, abnormal_price_ratio: 0.6, drop_highest_lowest: 1 },
      items: [], judges: [], bids: [], result: null, opening: false, clarifications: [], responses: {}, user: null,
      itemForm: { name: "", category: "tech", weight: 0.1, full_score: 10 },
      scoreForm: { bid_document_id: null, scores: {} },
    };
  },
  computed: {
    isBidder() { return this.user && this.user.role === "bidder"; },
    canManage() { return this.user && ["admin", "operator"].includes(this.user.role); },
  },
  async mounted() {
    this.sectionId = this.route.params.id;
    const res = await Api.get(`/api/sections/${this.sectionId}/evaluation`);
    this.rule = res.rule; this.items = res.items; this.judges = res.judges;
    this.bids = await Api.get(`/api/sections/${this.sectionId}/bids`);
    this.clarifications = await Api.get(`/api/sections/${this.sectionId}/evaluation/clarifications`);
    try { this.user = await Api.get("/api/auth/me"); } catch (e) { /* ignore */ }
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
      try { this.result = await Api.post(`/api/sections/${this.sectionId}/evaluation/open`); await this.reloadClarifications(); }
      catch (e) { alert(e.message); }
      finally { this.opening = false; }
    },
    async reloadClarifications() {
      this.clarifications = await Api.get(`/api/sections/${this.sectionId}/evaluation/clarifications`);
    },
    companyOfBid(id) {
      const bid = this.bids.find(b => b.id === id);
      return bid ? bid.company : `投标 ${id}`;
    },
    async submitClarification(c) {
      const content = this.responses[c.id];
      if (!content || !content.trim()) return alert("请填写澄清说明");
      try {
        await Api.post(`/api/clarifications/${c.id}/response`, { content });
        this.responses[c.id] = "";
        await this.reloadClarifications();
        alert("澄清说明已提交，等待审核");
      } catch (e) { alert(e.message); }
    },
    async reviewClarification(c, action) {
      const label = action === "accepted" ? "确认澄清成立并恢复报价有效性" : "认定澄清不成立并排除该异常报价";
      if (!confirm(`确认${label}？`)) return;
      const remark = prompt("处理备注（可留空）", "") || "";
      try {
        this.result = await Api.post(`/api/clarifications/${c.id}/review`, { action, remark });
        await this.reloadClarifications();
      } catch (e) { alert(e.message); }
    },
    async refresh() { const res = await Api.get(`/api/sections/${this.sectionId}/evaluation`); this.items = res.items; this.judges = res.judges; },
    fmtDate(d) { return d ? String(d).replace("T", " ").slice(0, 16) : "-"; },
  },
};
