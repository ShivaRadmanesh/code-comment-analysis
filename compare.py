# %%
from utils import *
import pickle as pkl


def analyze(repo_name: RepoName, separator: str = ""):
    # load data and check for invalid outputs
    with open(f"data/out/cleaned/{repo_name}.pkl", "rb") as fin:
        parsed_records: list[ParsedRecord] = pkl.load(fin)

    # analysis
    past_outdated: list[ParsedRecord] = []
    outdated: list[ParsedRecord] = []
    normal: list[ParsedRecord] = []
    for r in parsed_records:
        oc = r.record.commit_pair.old_comment
        nc = r.record.commit_pair.new_comment
        if oc != nc and r.result.old2new is False and r.result.new2new is False:
            past_outdated.append(r)
        elif r.result.old2new is True and r.result.new2new is False:
            outdated.append(r)
        elif (r.result.old2new is True and r.result.new2new is True) or (r.result.old2new is False and r.result.new2new is True):
            normal.append(r)
    # printing the result

    for name, segment in zip(["past_outdated", "outdated", "normal"], [past_outdated, outdated, normal]):
        print_info(f"{repo_name}:{name}", segment, separator)

    print_info(f"{repo_name}:total", parsed_records, separator=separator)
# %%


def statistics(repo_name: RepoName, separator: str = ""):
    with open(f"data/out/cleaned/{repo_name}.pkl", "rb") as fin:
        parsed_records: list[ParsedRecord] = pkl.load(fin)

    bi_commit_dict: dict[str, dict] = {}
    nbi_commit_dict: dict[str, dict] = {}
    past_outdated: list[ParsedRecord] = []
    outdated: list[ParsedRecord] = []
    normal: list[ParsedRecord] = []
    for r in parsed_records:
        oc = r.record.commit_pair.old_comment
        nc = r.record.commit_pair.new_comment
        status = "uncategorized"
        if oc != nc and r.result.old2new is False and r.result.new2new is False:
            past_outdated.append(r)
            status = "past_outdated"
        elif r.result.old2new is True and r.result.new2new is False:
            outdated.append(r)
            status = "outdated"
        elif (r.result.old2new is True and r.result.new2new is True) or (r.result.old2new is False and r.result.new2new is True):
            normal.append(r)
            status = "normal"

        if r.record.commit_pair.bug_introducing:
            if (log := bi_commit_dict.get(r.record.commit_pair.new_commit_hash, None)):
                if status in log:
                    log[status].append(r)
                else:
                    log[status] = [r]
            else:
                bi_commit_dict[r.record.commit_pair.new_commit_hash] = {
                    status: [r]}
        else:
            if (log := nbi_commit_dict.get(r.record.commit_pair.new_commit_hash, None)):
                if status in log:
                    log[status].append(r)
                else:
                    log[status] = [r]
            else:
                nbi_commit_dict[r.record.commit_pair.new_commit_hash] = {
                    status: [r]}

    for report in [bi_commit_dict, nbi_commit_dict]:
        for commit, log in report.items():
            for name, segment in zip(["past_outdated", "outdated", "normal", "uncategorized"], [log.get("past_outdated", None), log.get("outdated", None), log.get("normal", None), log.get("uncategorized", None)]):
                if not segment:
                    continue

                print_info(f"{repo_name}:{name}:{commit[:5]}", segment, separator)


# %%


header = f"| {'Name':^30} | {'14DaysBI':^10} | {'14DaysNBI':^10} | {'7DaysBI':^10} | {'7DaysNBI':^10} |"
separator = "-" * len(header)
print(separator)
print(header)
print(separator)
repo_names: list[RepoName] = ["archiva", "aries",
                              "cxf", "jena", "mesos", "storm", "karaf"]
for rn in repo_names:
    statistics(rn, separator)
# %%
