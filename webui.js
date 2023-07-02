'use strict'

let opts = window.aqm_opts, urls = window.aqm_urls

let d3js_api = opts.d3_api || 7,
	d3js_local_load = opts.d3_try_local || !opts.d3_from_cdn, // true = try local url first
	d3js_local_url = urls.d3,
	d3js_remote_load = opts.d3_from_cdn, // false = always use local copy
	d3js_remote_url = `https://d3js.org/d3.v${d3js_api}.min.js`,
	d3js_remote_import = `https://cdn.jsdelivr.net/npm/d3@${d3js_api}/+esm`,
	d3js_loader = async res => {
		if (window.d3) return window.d3
		if (d3js_local_load) {
			res = await fetch(d3js_local_url).catch(res => res)
			if (res.ok) { eval(await res.text()); return window.d3 } }
		else if (!d3js_remote_load) return
		if (!d3js_remote_load) return console.log(
			`ERROR: Failed to load local d3.js`
			+ ` [ ${d3js_local_url} ]: ${res.status} - ${res.statusText}` )
		if (d3js_local_load)
			console.log(`WARNING: importing d3 from ${d3js_remote_import}`)
		// XXX: check CSP settings on this
		return await import(d3js_remote_import) }

window.onload = () => d3js_loader().then(async d3 => {
if (!d3) return document.getElementById('graph').innerHTML = `
	<h2>ERROR: failed to load d3.js library</h2>
	<p>Check uMatrix/NoScript/adblocker setttings or put
		<a href='${d3js_remote_url}'>${d3js_local_url}</a> into same dir as main script.</p>`


let fmt_ts_tz, data, dss, ds_map, ds_text,
	ds_pmx = ['pm10', 'pm25', 'pm40', 'pm100'], ds_aux = ['voc', 'nox', 't', 'rh']
Data: {
	let fetch_samples = async ts => {
		if (!ts) ts = Date.now()
		let sbs = 24,
			sample_keys = ['ts', 'pm10', 'pm25', 'pm40', 'pm100', 'rh', 't', 'voc', 'nox'],
			sample_ks = [1, 10, 10, 10, 10, 100, 200, 10, 10],
			sample_nx = [-1, 0xffff, 0xffff, 0xffff, 0xffff, 0x7fff, 0x7fff, 0x7fff, 0x7fff],
			data_raw = new DataView(await fetch(urls.data).then(res => res.arrayBuffer()))
		return d3.range(0, data_raw.byteLength, sbs).map(n => {
			let vals = [data_raw.getFloat64(n)]
			vals.push.apply(vals, d3.range(n=n+8, n=n+2*4, 2).map(n => data_raw.getUint16(n)))
			vals.push.apply(vals, d3.range(n, n+2*4, 2).map(n => data_raw.getInt16(n)))
			vals = Object.fromEntries(
				d3.zip(sample_keys, vals, sample_ks, sample_nx)
					.map(([key, d, k, nx]) => [key, d === nx ? null : d / k]) )
			vals.ts = ts - vals.ts
			return vals }).sort((d1, d2) => d1.ts - d2.ts) }

	data = await fetch_samples()
	dss = d3.zip( ds_pmx,
			['PM1', 'PM2.5', 'PM4', 'PM10'],
			['#fdc28c', '#fc9346', '#eb6311', '#bb3d02'],
			[300, 400, 500, 700] )
		.map(([k, label, c, fw], n, ns) => ({
			k: k, label: label, color: c,
			line_w: 0.5 + 2.5 * (n / ns.length), font_w: fw }))
	d3.zip( ds_aux, ['VOC', 'NOx', 'T°C', 'RH%'],
			['#54e01150', '#41a6a280', '#d175c180', '#b31b7ce0'], [null, null, '5,5', '5,5'] )
		.forEach(([k, label, c, ld]) => dss.push({k: k, label: label, color: c, line_dash: ld}))
	dss = dss.filter(ds => data.some(d => d[ds.k] !== null)) // unsupported values

	fmt_ts_tz = Intl.DateTimeFormat().resolvedOptions().timeZone
	ds_map = Object.fromEntries(dss.map(ds => [ds.k, ds]))
	ds_map['ts'] = {k: 'ts', fmt: ts => new Intl.DateTimeFormat('sv-SE', {
		timeZone: fmt_ts_tz, year: 'numeric', month: '2-digit', day: '2-digit',
		hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(ts))}
	ds_pmx = ds_pmx.filter(k => ds_map[k])
	ds_aux = ds_aux.filter(k => ds_map[k])

	ds_text = ['ts'].concat(dss.map(ds => ds.k)) // list of text lines in order
} // Data


// Chart

let margin = {top: 20, right: 130, bottom: 50, left: 70},
	width = 960 - margin.left - margin.right,
	height = 700 - margin.top - margin.bottom,
	x = d3.scaleTime().range([0, width]).domain(d3.extent(data, d => d.ts)),
	y_pmx = d3.scaleLinear().range([height, 0]).domain(
		[0, d3.max(ds_pmx.map(k => data.map(d => d[k])).flat())] ),
	ys = Object.fromEntries(
		dss.map(ds => [ ds.k, ds_pmx.includes(ds.k) ? y_pmx :
			d3.scaleLinear().range([height, 0]).domain(d3.extent(data.map(d => d[ds.k]))) ]) ),
	ax = () => d3.axisBottom(x).ticks(8),
	ay_pmx = () => d3.axisLeft(y_pmx), // main Y axis
	ts_now_label = new Intl.DateTimeFormat('sv-SE', {
		timeZone: fmt_ts_tz, hour: '2-digit', minute: '2-digit',
		second: '2-digit', hour12: false }).format() + ' now'

let vis = d3.select('body svg')
		.attr('width', width + margin.left + margin.right)
		.attr('height', height + margin.top + margin.bottom)
	.append('g').attr('transform', `translate(${margin.left} ${margin.top})`)
	.call(s => {
		s.append('g').attr('class', 'x grid').call(
			ax().tickSize(height, 0).tickFormat('') )
		s.append('g').attr('class', 'y grid').call(
			ay_pmx().tickSize(-width, 0).tickFormat('') ) })
	.call( s => s
		.append('g')
			.attr('class', 'x axis').attr('transform', `translate(0 ${height})`)
			.call(ax())
		.append('text')
			.attr('transform', `translate(${width} 0)`)
			.attr('dx', '-1em').attr('dy', '3em')
			.style('text-anchor', 'end').text(
				`Date/time in local/browser timezone (${fmt_ts_tz}, ${ts_now_label})` ) )
	.call( s => s
		.append('g').attr('class', 'y axis').call(ay_pmx())
		.append('text')
			.attr('transform', 'rotate(-90)').attr('dx', '-1em').attr('dy', '-3em')
			.style('text-anchor', 'end').text('PMx µg/m³') )
	.call( s => ds_aux.forEach((k, n) =>
		s.append('g').attr('class', 'y axis')
			.attr('transform', `translate(${width + n*30} 0)`)
			.call(d3.axisRight(ys[k]))
			.call(s => s.selectAll('text')
				.style('text-anchor', 'middle')
				.attr('transform', 'rotate(60) translate(-3 -13)'))
			.append('text')
				.attr('transform', 'rotate(-90)').attr('dx', -(height+10)).attr('dy', '1.5em')
				.style('text-anchor', 'end').text(ds_map[k].label)) )
	.call(s => dss.forEach(ds => ds.line = s.append('path')
		.data([data]).attr('class', `line ${ds.k}`).attr('stroke', ds.color || 'currentColor')
		.attr('stroke-width', ds.line_w || null).attr('stroke-dasharray', ds.line_dash || null)
		.attr('d', d3.line().x(d => x(d.ts)).y(d => ys[ds.k](d[ds.k]))) ))


Focus: {
	let side = -1, // 1 or -1
		x_bisect = d3.bisector(d => d.ts).left,
		focus = vis
			.append('g').attr('class', 'focus').style('display', 'none')
			.call( s => s.append('line')
				.attr('x1', 0).attr('x2', 0).attr('y1', 0).attr('y2', height) ),
		focus_label = focus.append('text')
			.attr('x', 10).attr('dy', '.3em')
			.attr('text-anchor', side > 0 ? 'start' : 'end')

	let del_p,
		del_ps = data.map(d => dss.map(ds => [x(d.ts), ys[ds.k](d[ds.k]), ds])).flat(),
		del = d3.Delaunay.from(del_ps)
	// vis.append('g').selectAll('path').data(del.voronoi([0, 0, width, height]).cellPolygons())
	// 	.join( en => en.append('path').attr('stroke', 'red')
	// 		.attr('fill', 'none'), upd => upd, ex => ex.remove() )
	// 	.attr('d', d => d ? 'M' + d.join('L') + 'Z' : null)

	let fmt_n = n => n.toFixed(1),
		fmt_line = (d, k) => { let label = ds_map[k]?.label
			return `${label ? (label+': ') : ''}${(ds_map[k]?.fmt || fmt_n)(d[k])}` }

	let focus_hl_line = (hl_set=(k,a,b)=>b) => dss.forEach( ds =>
		ds.line?.attr('stroke', hl_set(ds.k, 'currentColor', ds.color))
			.attr('stroke-width', hl_set(ds.k, 2, ds.line_w || null)) )

	vis.append('rect')
		.attr('class', 'overlay').attr('width', width).attr('height', height)
		.on('mouseover', (ev, d) => focus.style('display', null))
		.on('mouseout', (ev, d) => { focus.style('display', 'none'); focus_hl_line() })
		.on('mousemove', (ev, d) => {
			if (data.length < 2) return
			let [px, py] = d3.pointer(ev),
				x0 = x.invert(px), n = x_bisect(data, x0, 1)
			if (x0 - data[n-1].ts <= data[n] - x0) n -= 1
			d = data[n]

			let hl_set = del_ps[del_p = del.find(px, py, del_p)][2]
			focus_hl_line(hl_set = ( k_hl =>
				(k, hl=true, no_hl=null) => (k_hl && k === k_hl) ? hl : no_hl )(hl_set?.k))

			focus.attr('transform', `translate(${x(d.ts)} 0)`)
			focus_label.selectAll('tspan').call( s => s
				.data(ds_text.filter(k => d[k] !== null), d => d)
				.join(
					en => en.append('tspan')
						.attr('dy', '1.5em').attr('x', `${side}em`)
						.attr('fill', k => ds_map[k].color?.slice(0, 7) || 'currentColor')
						.attr('font-weight', k => ds_map[k]?.font_w || null),
					upd => upd, ex => ex.remove() )
				.text(k => fmt_line(d, k)).classed('hl', k => hl_set(k)) ) })
} // Focus

})
