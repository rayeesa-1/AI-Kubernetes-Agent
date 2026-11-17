PHASE 5 UPDATE — MERGE INTO YOUR EXISTING PROJECT

1. Back up your ai-kubernetes-agent folder.
2. Extract this ZIP into that folder, merging folders and replacing matching files.
   It contains changed/new files only, not a complete standalone application.
   Keep .env, kubeconfig, Compose, Dockerfiles and other existing files.
   It does not replace your signup/authentication files.
3. Read docs/PHASE5-START-HERE.md before rebuilding.
4. Run deploy/insforge-phase5.sql in the existing project's InsForge SQL Editor.
5. In Windows PowerShell run scripts/Export-BackendKubeconfig.ps1.
6. Run docker compose up -d --build.
7. Open localhost:3000, sign in, select a cluster/context, investigate.
8. Follow the documented live tests; intentional failures are never auto-applied.

Add the patterns in .gitignore-phase5.txt to your current .gitignore.
Results and limitations are listed in docs/PHASE5-VALIDATION.txt.
