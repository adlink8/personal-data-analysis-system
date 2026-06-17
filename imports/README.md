# 增量导入入口

把新导出的文件先放到这里：

```text
imports/
  incoming/
    google/
    gpt/
```

然后从工作区根目录运行：

```powershell
python 统合模块\脚本\run_import_pipeline.py --source google --input imports\incoming\google
python 统合模块\脚本\run_import_pipeline.py --source gpt --input imports\incoming\gpt
```

脚本会创建批次目录：

```text
imports/batches/<batch_id>/
  raw/
  extracted/
  manifest.json
  import_log.json
```

重复文件不会删除，会移动到：

```text
imports/duplicate_audit/quarantine/
```

