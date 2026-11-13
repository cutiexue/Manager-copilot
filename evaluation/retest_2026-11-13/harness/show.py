import json, sys, glob
E = sys.argv[1]; want = set(sys.argv[2].split(','))
exp = json.load(open(f'{E}/report_expectations.json'))
for path in sorted(glob.glob(f'{E}/report_questions/scenarios/*.json')):
    r = json.load(open(path))
    if not want & set(r['questions']): continue
    print(f"\n######## {r['scenario']}  {('['+r['adaptation']+']') if r['adaptation'] else ''}")
    for s in r['steps']:
        k = s['step']
        if k == 'chat':
            q = s.get('qid')
            if q: print(f"--- {q} report={exp[q]['report_disposition']} | expected: {exp[q]['expected'] or exp[q]['observed'][:300]}")
            print(f">> {s['message']}")
            rep = s['reply']
            print("ANSWER:", (rep.get('answer') or json.dumps(rep))[:2500])
            print("TOOLS:", [(c['name'], {a: v for a, v in (c.get('arguments') or {}).items() if a != 'text'}, c.get('status')) for c in rep.get('tool_calls', [])])
            ch = rep.get('answer_check') or {}
            if ch.get('unverified') or ch.get('retried'): print("CHECK:", ch)
            if rep.get('proposals'): print("PROPOSALS:", [(p['kind'], p['status'], p['summary'][:140]) for p in rep['proposals']])
        elif k == 'state':
            st = s['state']
            print("STATE: props", [(p['kind'], (p.get('payload') or {}).get('order_id'), (p.get('payload') or {}).get('text', '')[:30], p['status']) for p in st['/actions']],
                  "| notes", [(n.get('order_id'), n.get('text')) for n in st['/notes']], "| reminders", [(x.get('remind_at'), x.get('status')) for x in st['/reminders']],
                  "| drafts", len(st['/drafts']), "| watches", [(w.get('order_id'), w.get('deadline'), w.get('status')) for w in st['/watches']],
                  "| alerts", [(a.get('kind'), a.get('title')[:60]) for a in st['/alerts']], "| audit", [a.get('event') for a in st['/audit']])
        elif k in ('confirm', 'cancel', 'confirm_twice', 'confirm_concurrent'):
            print(f"{k.upper()}:", (s.get('proposal') or {}).get('summary', '')[:80], [(x['http_status'], (x['body'].get('proposal') or {}).get('status') if isinstance(x['body'], dict) else None, (x['body'].get('detail') if isinstance(x['body'], dict) else None)) for x in s.get('responses', [])], s.get('error', ''))
        elif k == 'advance':
            b = s['response']['body']; print("ADVANCE:", s['response']['http_status'], b.get('current', {}).get('version'), json.dumps(b.get('check'))[:300])
        elif k in ('watch_check', 'fire_reminders', 'expire'):
            print(f"{k.upper()} @{s.get('at')}:", json.dumps(s.get('result'))[:300])
        else:
            print(k.upper(), {kk: v for kk, v in s.items() if kk not in ('step', 'seconds')})
        if s.get('exception'): print("EXCEPTION:", s['exception'][-300:])
