import sys, os, json, hashlib, collections
mods, repo, evid, out = sys.argv[1:5]
def shas(p):
    b = open(p, 'rb').read(); lf = b.replace(b'\r\n', b'\n')
    return {hashlib.sha256(x).hexdigest() for x in (b, lf, lf.replace(b'\n', b'\r\n'))}
PINS = {'oracle_semantics_v2.py': 'aa85f4953bea36974b77340c38fe8219e5a8d577d5e786ff74c06de2fc07423d', 'oracle_confirmation.py': '4609a2256d0803c1029fae572db62c28f6885b8a12628094a9e10bcb65b752d1'}
for f, pin in PINS.items():
    if pin not in shas(os.path.join(mods, f)): sys.exit('STOP: classifier pin mismatch ' + f)
EVM = os.path.join(evid, 'JUNIT_EVIDENCE_MANIFEST.json')
EVSHA = hashlib.sha256(open(EVM, 'rb').read()).hexdigest()
if EVSHA != '39ea5470625188a4357575f971842676d32a3ee811874d256f7978e1989b3647': sys.exit('STOP: evidence manifest hash mismatch')
ev = json.load(open(EVM, encoding='utf-8'))
for key, src, rel, h, n in ev['files']:
    if hashlib.sha256(open(os.path.join(evid, rel), 'rb').read()).hexdigest() != h: sys.exit('STOP: evidence file changed ' + rel)
sys.path.insert(0, mods)
import oracle_semantics_v2 as S, oracle_confirmation as C
man = json.load(open(os.path.join(repo, 'research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json'), encoding='utf-8-sig'))
mt = {t['task_id']: t for t in man['per_task']}
pos = sorted(t for t in mt if mt[t]['f2p']['total'] > 0)
v2 = {}
for l in open(os.path.join(repo, 'research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl'), encoding='utf-8-sig'):
    if l.strip():
        r = json.loads(l); v2[r['task_id']] = r
base = os.path.join(evid, 'junit/opt/wp2_v2/c2_artifact_rescue')
canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
tasks, fails = [], []
for tid in pos:
    s = tid.split('saleor-rc-')[1][:12]; nf = v2[tid]['n_test_files']
    st, runs = {}, collections.defaultdict(lambda: {'t': [], 'p': []})
    for state in ('t', 'p'):
        merged, mfail = {}, {}
        for rep in range(3):
            for idx in range(nf):
                f = os.path.join(base, f'{s}_{state}', f'{s}_{state}_r{rep}_f{idx}.xml')
                if not os.path.exists(f): sys.exit('STOP: missing junit ' + f)
                nodes, fl = C.parse_junit_with_failures(open(f, encoding='utf-8').read())
                merged.update(nodes); mfail.update(fl)
                for n, o in nodes.items(): runs[n][state].append(o)
        st[state] = (merged, mfail)
    (tg, _), (pa, pf) = st['t'], st['p']
    allnodes = sorted(set(tg) | set(pa)); cnt = collections.Counter(); beh, sym = [], []
    for n in allnodes:
        c = S.classify_node_v2(target_outcomes=[tg.get(n, 'missing')] * 3, parent_outcomes=[pa.get(n, 'missing')] * 3,
                               parent_failure_text=pf.get(n, ''), parent_collects_node=n in pa, shared_test_support_failed=n not in pa)
        cnt[c] += 1
        if c == 'BEHAVIORAL_F2P': beh.append(n)
        if c == 'SYMBOL_ABSENCE_F2P': sym.append(n)
    fro = v2[tid]['counts']
    exact = all(cnt.get(k, 0) == fro[k] for k in fro) and len(allnodes) == v2[tid]['n_nodes']
    if not exact: fails.append(tid)
    unstable = sorted(n for n in beh + sym if runs[n]['t'] != ['passed'] * 3 or any(o not in ('failed', 'error') for o in runs[n]['p']) or len(runs[n]['p']) != 3)
    ident = {'task_id': tid, 'behavioral_f2p': sorted(beh), 'symbol_absence_f2p': sorted(sym)}
    tasks.append({**ident, 'node_identity_sha256': hashlib.sha256(canon(ident).encode()).hexdigest(),
                  'frozen_counts': fro, 'replay_exact_count_match': exact, 'n_nodes': len(allnodes),
                  'primary_behavioral_frozen': mt[tid]['f2p']['behavioral'] > 0,
                  'f2p_nodes_not_stable_across_3_recorded_runs': unstable,
                  'spec_3run_primary_eligible': (len(beh) - len([n for n in unstable if n in beh])) >= 1})
if fails: sys.exit('STOP: count mismatch ' + ','.join(fails))
agg = hashlib.sha256(canon([t['node_identity_sha256'] for t in tasks]).encode()).hexdigest()
doc = {'artifact': 'OPWS_F2P_NODE_CONTRACT_83', 'schema': 'opws-f2p-node-contract/1.0', 'status': 'PROPOSED_PENDING_OWNER_SIGNOFF',
       'source_evidence_manifest_sha256': EVSHA, 'classifier_semantics_sha256': PINS['oracle_semantics_v2.py'],
       'classifier_bundle_recorded': 'b11374fe35e5f40d27962dfe777e7a84b666fb0d32374c74f744cdd6eea1395e',
       'replay_rule': 'frozen wp2_linux_dryrun.run_state_in_container merge order (rep-major, file-minor, last-write-wins) + frozen classify_node_v2 with [last]*3',
       'node_identity_recipe': "sha256(json.dumps({task_id,behavioral_f2p(sorted),symbol_absence_f2p(sorted)},sort_keys=True,ensure_ascii=False,separators=(',',':')))",
       'aggregate_recipe': 'sha256(canonical json list of node_identity_sha256 in sorted task_id order)',
       'n_tasks': len(tasks), 'n_exact_count_match': sum(t['replay_exact_count_match'] for t in tasks),
       'n_behavioral_f2p_nodes': sum(len(t['behavioral_f2p']) for t in tasks), 'n_symbol_absence_f2p_nodes': sum(len(t['symbol_absence_f2p']) for t in tasks),
       'n_tasks_with_3run_instability': sum(1 for t in tasks if t['f2p_nodes_not_stable_across_3_recorded_runs']),
       'n_primary_frozen': sum(t['primary_behavioral_frozen'] for t in tasks), 'n_primary_spec_3run': sum(t['spec_3run_primary_eligible'] for t in tasks),
       'aggregate_node_contract_sha256': agg, 'real_opws_behavioral_outcomes': 0, 'tasks': tasks}
data = (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
open(out, 'wb').write(data)
print('tasks', doc['n_tasks'], 'exact', doc['n_exact_count_match'], 'beh', doc['n_behavioral_f2p_nodes'], 'sym', doc['n_symbol_absence_f2p_nodes'])
print('3run-unstable tasks', doc['n_tasks_with_3run_instability'], '| primary frozen', doc['n_primary_frozen'], '| primary spec-3run', doc['n_primary_spec_3run'])
print('AGGREGATE_NODE_CONTRACT_SHA256', agg)
print('FILE_SHA256', hashlib.sha256(data).hexdigest())
