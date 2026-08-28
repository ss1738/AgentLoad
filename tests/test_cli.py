import json, subprocess, sys
from agentload.cli import EXIT_EXECUTION_FAILED, EXIT_INVALID_CONFIG, EXIT_OK, EXIT_THRESHOLD

def cli(*args): return subprocess.run([sys.executable, '-m', 'agentload.cli', *args], text=True, capture_output=True)
def test_help_and_invalid_config():
    assert cli('--help').returncode == EXIT_OK
    result=cli('run','missing.yml','--host','http://x'); assert result.returncode == EXIT_INVALID_CONFIG and 'Traceback' not in result.stderr
    assert cli('analyze','missing.jsonl','--threshold','2').returncode == EXIT_INVALID_CONFIG
def test_analysis_threshold_contract(tmp_path):
    path=tmp_path/'traces.jsonl'; path.write_text(json.dumps({'concurrency':1,'latency_ms':1,'http_status':200,'task_success':False,'failure_category':'success_assertion_failed'})+'\n')
    normal=cli('analyze',str(path),'--threshold','.9'); assert normal.returncode == EXIT_OK and 'Breaking point: 1' in normal.stdout
    failed=cli('analyze',str(path),'--threshold','.9','--fail-under-threshold','--output',str(tmp_path/'out')); assert failed.returncode == EXIT_THRESHOLD and (tmp_path/'out'/'report.json').exists()
    assert cli('analyze',str(tmp_path/'none'),'--threshold','.9').returncode == EXIT_EXECUTION_FAILED
