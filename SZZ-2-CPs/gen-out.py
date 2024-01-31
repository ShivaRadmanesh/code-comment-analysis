import json
import dataclasses
import os
from dataclasses import dataclass
from datetime import timedelta
from random import sample

import git
import javalang as jl
from git import GitCommandError
import re



REPO_BASE = "szzy_repos/"
COMMITS_BASE = "repo-info/"
SZZ_OUT_BASE = "szz-in/"
OUT_BASE = "out/"


@dataclass
class CommitPair:
    old_commit_hash: str
    new_commit_hash: str
    old_method_content: str
    new_method_content: str
    old_comment: str
    new_comment: str
    file_path: str
    bug_introducing: bool
    old_commit_date: str
    new_commit_date: str
    _id: str


def _my_get_string(content, node: jl.tree.MethodDeclaration):
    start = node.position
    start_pos = start.line - 1
    lines = content.splitlines(True)
    if node.body is None:
        code = lines[start_pos]
        end_pos = start_pos
        while ';' not in code:
            end_pos += 1
            code = code + lines[end_pos]
        return code

    if not node.body:
        end_pos = start_pos
    else:
        last_elem = node.body[-1]
        end_pos = last_elem.position.line - 1

    if end_pos == start_pos:
        end_pos += 1

    code = "".join(lines[start_pos:end_pos])
    no_comment_code = remove_comments(code)
    while no_comment_code.count("{") != no_comment_code.count("}"):
        end_pos += 1
        code = code + lines[end_pos]
        no_comment_code = remove_comments(code)

    return code


def remove_comments(input_text):
    comment_matches = []
    comments_pattern = re.compile(
        r'(//.*?$)|(/\*.*?\*/)', re.MULTILINE | re.DOTALL)
    strings_pattern = re.compile(r'[^\\](".*?(?<!\\\\)[^\\]")')

    comments_matcher = comments_pattern.finditer(input_text)
    for match in comments_matcher:
        start, end = match.span()
        comment_matches.append((start, match.group()))

    comments_to_remove = []
    strings_matcher = strings_pattern.finditer(input_text)
    for string_match in strings_matcher:
        for comment in comment_matches:
            if string_match.start() < comment[0] < string_match.end():
                comments_to_remove.append(comment)

    for comment in comments_to_remove:
        comment_matches.remove(comment)

    for comment in comment_matches:
        input_text = input_text.replace(comment[1], " ")

    return input_text


def __get_comment_if_any(start, content):
    comment = ""
    block_comment = False
    line_comment = False
    pos = start.line - 2
    lines = content.splitlines(True)
    while pos >= 0:
        current_line = lines[pos]
        if block_comment:
            if "/*" in current_line:
                comment = current_line + comment
                pos -= 1
                break
            else:
                comment = current_line + comment
                pos -= 1
                continue

        if line_comment:
            if "//" in current_line:
                comment = current_line + comment
                pos -= 1
                continue
            else:
                break

        if current_line.strip() == "" or current_line.strip().startswith("@"):
            pos -= 1
            continue
        elif "*/" in current_line:
            block_comment = True
            comment = current_line + comment
            pos -= 1
            continue
        elif "//" in current_line:
            line_comment = True
            comment = current_line + comment
            pos -= 1
            continue
        else:
            break
    return comment.strip()


def compare_commits(repo_path, old_commit, new_commit, bug_introducing):
    repo = git.Repo(repo_path)
    
    # Getting some general info
    global project_name
    old_commit_date = str(repo.commit(old_commit).committed_datetime)
    new_commit_date = str(repo.commit(new_commit).committed_datetime)
    
    # accessing a global id counter
    global _id

    # Getting git diff of the two files
    diff = repo.git.diff(old_commit, new_commit)
    file_names = [(line.split(" b/")[0].split(" a/")[-1].strip(), line.split(" b/")[-1].strip()) for line in
                  diff.splitlines() if line.startswith("diff --git")]

    # Considering only files that are not renamed and end with java
    file_names = [x for x, y in file_names if x == y and x.endswith(".java")]

    info = {
        "total_files": len(file_names),
        "project": project_name,
        "old_commit": old_commit,
        "new_commit": new_commit,
        "file_parse_erros": [],
        "method_parse_errors": []
    }
    pairs = []
    for file_name in file_names:
        try:
            content_old = repo.git.show(f"{old_commit}:{file_name}")
            content_new = repo.git.show(f"{new_commit}:{file_name}")
        except GitCommandError as e:
            # print(e, file=sys.stderr)
            continue
        try:
            tree_old = jl.parse.parse(content_old)
            tree_new = jl.parse.parse(content_new)
        except Exception as e:
            print(f"Error Parsing file {file_name} skipping")
            info["file_parse_erros"].append({
                "filename": file_name,
                "error": str(e)
            })
            continue

        methods_old, comments_old, methods_new, comments_new = {}, {}, {}, {}
        for _, node in tree_old.filter(jl.tree.MethodDeclaration):
            try:
                methods_old[node.name] = _my_get_string(content_old, node)
                comments_old[node.name] = __get_comment_if_any(
                    node.position, content_old)

            except Exception as e:
                info["method_parse_errors"].append({
                    "filename": file_name,
                    "method_name": node.name,
                    "old_commit": True,
                    "error": str(e)
                })
                continue

        for _, node in tree_new.filter(jl.tree.MethodDeclaration):
            try:
                methods_new[node.name] = _my_get_string(content_new, node)
                comments_new[node.name] = __get_comment_if_any(
                    node.position, content_new)
            except Exception as e:
                info["method_parse_errors"].append({
                    "filename": file_name,
                    "method_name": node.name,
                    "old_commit": False,
                    "error": str(e)
                })
                continue

        method_names_old = set(methods_old.keys())
        method_names_new = set(methods_new.keys())

        common_methods = method_names_old.intersection(method_names_new)
        info["common_methods"] = list(common_methods)

        for m in common_methods:
            p = CommitPair(old_commit, new_commit, methods_old[m], methods_new[m], comments_old[m], comments_new[m],
                           file_name, bug_introducing, old_commit_date, new_commit_date, f"{project_name}_{_id}")
            _id += 1
            pairs.append(p)

    return pairs, info


def get_commits_before(repo_path, target_commit, window):
    repo = git.Repo(repo_path)
    target_commit = repo.commit(target_commit)
    window_start = target_commit.committed_datetime - timedelta(days=window)

    commits_before = []
    window_end = target_commit.committed_datetime

    for commit in repo.iter_commits(rev='HEAD'):
        if window_start < commit.committed_datetime < window_end:
            commits_before.append(commit)

    return commits_before


def extract_javadoc_explanation(input_string):
    # Define a regular expression pattern to match Javadoc comments
    javadoc_pattern = r"/\*\*(.*?)\*/"

    # Find all Javadoc comments in the input string
    javadoc_matches = re.findall(javadoc_pattern, input_string, re.DOTALL)
    if javadoc_matches:
        javadoc_match = javadoc_matches[0]
        cleaned_text = re.sub(
            r'^\s*\* ?', '', javadoc_match, flags=re.MULTILINE)

        # Split the Javadoc comment into lines
        lines = cleaned_text.split('\n')

        # Remove leading and trailing whitespace from each line
        lines = [line.strip() for line in lines]

        # Remove empty lines
        lines = [line for line in lines if line]

        # Remove lines that start with '@see' or '{@'
        lines = [line for line in lines if not line.startswith(
            '@see') and not line.startswith("{@")]

        # Join the remaining lines to form the explanation
        explanation = '\n'.join(lines)

        return explanation
    else:
        return ""


def remove_special_characters(input_string):
    pattern = r'[\n\r\t\x00-\x1F\x7F-\x9F\xA0—–…•©®° ]'

    cleaned_string = re.sub(pattern, '', input_string)

    return cleaned_string




def main():
    file_id = os.getenv("SLURM_ARRAY_TASK_ID", None)
    assert file_id is not None
    with open(SZZ_OUT_BASE+f"{file_id}.json", 'r') as f:
        data = json.load(f)

    global project_name
    project_name = data[0]["repo_name"]

    with open(COMMITS_BASE+f"{project_name}.txt", 'r') as f:
        # Read all lines and remove any leading/trailing whitespace
        commits = [line.strip() for line in f.readlines()]

    print(f"Working on project {project_name}")
    BIC = [d['inducing_commit_hash'][0]
           for d in data if d['inducing_commit_hash']]
    normal_commits = [c for c in commits if c not in BIC]

    sample_size = min(34, len(BIC), len(normal_commits))

    sampled = sample(normal_commits, sample_size)
    bic_sampled = sample(BIC, sample_size)

    sampled = [(x, 0) for x in sampled]
    bic_sampled = [(x, 1) for x in bic_sampled]

    commit_ambari = bic_sampled + sampled
    print("Commit samples created", len(commit_ambari))

    repo_path = REPO_BASE+project_name+"/"

    res = [] # type: list[CommitPair]
    global _id
    _id = 0
    final_reports = []
    for i, target_commit in enumerate(commit_ambari):
        print(f"Working on {i}/{len(commit_ambari)} commit", flush=True)
        commits = get_commits_before(repo_path, target_commit[0], 14)

        for commit in commits:
            pairs, info = compare_commits(repo_path, commit.hexsha, target_commit[0], target_commit[1])
            res.extend(pairs)
            final_reports.append(info)

    # saving raw data
    with open(OUT_BASE+project_name+".json", "w+") as resout:
        dicts = [dataclasses.asdict(x) for x in res]
        json.dump(dicts, resout)

    with open(OUT_BASE+"infos/"+project_name+".json", "w+") as infout:
        json.dump(final_reports, infout)

    # cleanning data

    cleanned_data = []
    for cp in res:
        if remove_special_characters(cp.old_method_content) != remove_special_characters(cp.new_method_content): # methods differ
            if extract_javadoc_explanation(cp.old_comment) != "" : # old comment has non-empty java doc
                if extract_javadoc_explanation(cp.new_comment) != "" : # new comment has non-empty java doc
                    cleanned_data.append(cp)
    
    print(f"cleanned_data: {len(cleanned_data)}, original_data: {len(res)}. Removed {len(res) - len(cleanned_data)}")
    with open(OUT_BASE+"cleaned/"+project_name+".json", 'w+') as cout:
        dicts = [dataclasses.asdict(x) for x in cleanned_data]
        json.dump(dicts, cout)


if __name__ == '__main__':
    main()


