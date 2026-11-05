-- 显式回退仅删除研究索引；调用前备份，归档对象保留以便恢复。
DROP TABLE research_hops;
DROP TABLE research_results;
DROP TABLE research_evidence;
DROP TABLE research_runs;
