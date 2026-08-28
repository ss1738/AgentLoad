import json
import pytest
from agentload.analyze import AnalysisError, build_report_from_stages, markdown_report
from agentload.trace import FailureCategory, Trace, write_traces

def stage(root, users, status, duration, traces):
    directory=root/'stages'; directory.mkdir(exist_ok=True)
    write_traces(directory/f'concurrency-{users}.jsonl', traces)
    (directory/f'concurrency-{users}.meta.json').write_text(json.dumps({'concurrency':users,'status':status,'configured_duration_seconds':60,'observed_duration_seconds':duration,'trace_count':len(traces)}))

def test_three_stage_synthetic_report(tmp_path):
    stage(tmp_path,1,'completed',30,[Trace(1,1,200,True) for _ in range(10)])
    stage(tmp_path,10,'completed',60,[Trace(10,1,200,True) for _ in range(7)]+[Trace(10,1,429,False,failure_category=FailureCategory.HTTP_429) for _ in range(2)]+[Trace(10,1,None,False,failure_category=FailureCategory.TIMEOUT)])
    stage(tmp_path,25,'failed',12,[Trace(25,1,500,False,failure_category=FailureCategory.HTTP_5XX) for _ in range(3)])
    report=build_report_from_stages(tmp_path,.9,'synthetic')
    assert report['aggregate_trace_count']==23 and report['highest_passing_concurrency']==1 and report['breaking_point']==10 and report['incomplete_stages']==[25]
    one, ten, twentyfive=report['stages']; assert one['successful_tasks_per_minute']==20 and ten['successful_tasks_per_minute']==7 and twentyfive['successful_tasks_per_minute'] is None
    assert ten['failure_counts']['http_429']==2 and ten['failure_counts']['timeout']==1 and sum(ten['failure_counts'].values())==3
    text=markdown_report(report); assert 'Incomplete stages retained' in text and '| 25 | failed |' in text and 'http_429' in text

def test_stage_pair_and_count_errors(tmp_path):
    (tmp_path/'stages').mkdir(); (tmp_path/'stages'/'concurrency-1.meta.json').write_text('{}')
    with pytest.raises(AnalysisError, match='paired'): build_report_from_stages(tmp_path,.9)
    (tmp_path/'stages'/'concurrency-1.meta.json').unlink()
    stage(tmp_path,2,'completed',1,[Trace(2,1,200,True)])
    (tmp_path/'stages'/'concurrency-2.meta.json').write_text('{bad')
    with pytest.raises(AnalysisError, match='malformed metadata'): build_report_from_stages(tmp_path,.9)
