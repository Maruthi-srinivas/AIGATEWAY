# Tradeoffs

- Plain manifests instead of Helm. The install is readable and kubeconform can check it. There is no chart values file.
- kubeconform in CI instead of a kind cluster. A bad manifest fails the job. The job does not prove the pods start.
- Faithfulness under 95% is recorded on the evaluation report and does not fail CI. A case error or a null faithfulness score still fails the suite.
- Cost is a counter labeled by model, plus a tenant summary API. There is no new page in the web console.
- Key rotation is a restart. The gateway does not accept two secrets at once.
- Audit rows are append-only because no delete route exists. There is no hash chain.
