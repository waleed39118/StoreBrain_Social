// Owner/manager dashboard: today's KPIs, 7-day chart, top sellers and analytics tabs.
import { api } from '../api.js';
import { h, mount, svg, toast, fmtMoney } from '../dom.js';
import { t, pname } from '../i18n.js';

export async function render(root) {
  const tabsBox = h('div', { class: 'card' });
  let d;
  try { d = await api('/dashboard/summary'); } catch (e) { toast(t('error_generic', { m: e.message }), 'error'); return; }
  const cur = d.currency;
  const kpi = (label, value, href) => h(href ? 'a' : 'div', { class: 'kpi card', href }, h('small', { class: 'muted' }, label), h('strong', {}, value));

  mount(root, h('div', { class: 'stack' },
    h('div', { class: 'kpis' },
      kpi(t('today_revenue'), fmtMoney(d.today.revenue, cur)), kpi(t('today_sales'), String(d.today.sales)),
      kpi(t('avg_ticket'), fmtMoney(d.today.avg_ticket, cur)), kpi(t('items_sold'), String(d.today.items)),
      kpi(t('low_stock'), String(d.low_stock), '#/products'), kpi(t('unread_alerts'), String(d.unread_alerts), '#/alerts')),
    h('div', { class: 'two-col' },
      h('div', { class: 'card' }, h('h2', {}, t('last7')), barChart(d.last_7_days, cur)),
      h('div', { class: 'card' }, h('h2', {}, t('top_today')),
        d.top_today.length ? h('ol', { class: 'top-list' }, d.top_today.map(p => h('li', {}, h('span', {}, pname(p)), h('strong', {}, String(p.quantity)))))
          : h('p', { class: 'muted' }, t('nothing_here')))),
    tabsBox));

  const tabs = [['reorder', t('reorder_list')], ['best', t('best_sellers')], ['obsolete', t('obsolete')], ['div', t('diversify')]];
  let active = 'reorder';
  async function drawTab() {
    const head = h('div', { class: 'tabs', role: 'tablist' }, tabs.map(([k, l]) =>
      h('button', { role: 'tab', 'aria-selected': String(k === active), class: k === active ? 'tab active' : 'tab', onclick: () => { active = k; drawTab(); } }, l)));
    mount(tabsBox, head, h('div', { class: 'loading' }, t('loading')));
    try {
      let body;
      if (active === 'reorder') {
        const rows = await api('/analytics/reorder');
        body = table([t('name'), t('stock'), t('days_cover'), t('order_qty'), t('est_cost')],
          rows.map(r => [r.name_en, r.stock_qty, r.days_of_cover == null ? '∞' : r.days_of_cover.toFixed(1), h('strong', {}, String(r.order_qty)), fmtMoney(r.est_cost ?? 0, cur)]));
      } else if (active === 'best') {
        const rows = await api('/analytics/best-sellers');
        body = table([t('name'), t('units'), t('revenue'), t('trend')],
          rows.map(r => [pname(r), r.units, fmtMoney(r.revenue, cur), r.trend_pct == null ? '—' : `${r.trend_pct > 0 ? '▲' : r.trend_pct < 0 ? '▼' : '•'} ${Math.abs(r.trend_pct)}%`]));
      } else if (active === 'obsolete') {
        const rows = await api('/analytics/obsolete');
        body = table([t('name'), t('condition')], rows.map(r => [r.name_en, r.flags.join(' • ')]));
      } else {
        const r = await api('/analytics/diversification');
        body = h('div', { class: 'stack' }, h('p', {}, `HHI: ${r.hhi ?? '—'} • ${r.concentration}`),
          h('ul', {}, r.recommendations.map(x => h('li', {}, x))),
          table([t('category'), t('units'), t('revenue'), '%'], r.categories.map(c => [c.category, c.units, fmtMoney(c.revenue, cur), `${(c.share * 100).toFixed(1)}%`])));
      }
      mount(tabsBox, head, body);
    } catch (e) { mount(tabsBox, head, h('p', { class: 'error' }, e.message)); }
  }
  drawTab();
}

function table(cols, rows) {
  if (!rows.length) return h('p', { class: 'muted' }, t('nothing_here'));
  return h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, cols.map(c => h('th', {}, c)))),
    h('tbody', {}, rows.map(r => h('tr', {}, r.map(c => h('td', {}, c instanceof Node ? c : String(c))))))));
}

function barChart(days, cur) {
  const max = Math.max(1, ...days.map(d => Number(d.revenue)));
  const W = 420, H = 180, pad = 24, bw = (W - pad * 2) / days.length;
  return svg('svg', { viewBox: `0 0 ${W} ${H + 30}`, class: 'chart', role: 'img', 'aria-label': t('last7') },
    days.map((d, i) => {
      const v = Number(d.revenue), bh = (v / max) * H;
      const x = pad + i * bw + 6, y = H - bh + 4;
      return svg('g', {},
        svg('rect', { x, y, width: bw - 12, height: Math.max(bh, 1), rx: 4, class: i === days.length - 1 ? 'bar today' : 'bar' },
          svg('title', {}, `${d.date}: ${fmtMoney(v, cur)}`)),
        svg('text', { x: x + (bw - 12) / 2, y: H + 22, 'text-anchor': 'middle', class: 'axis' }, d.date.slice(5)));
    }));
}
