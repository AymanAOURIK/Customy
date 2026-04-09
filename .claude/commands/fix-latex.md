# /fix-latex

Fix a LaTeX compilation error in the last generated `resume.tex`.

Steps:

1. Read the last `resume.tex` from the output folder.
2. Read the `pdflatex` error log.
3. Fix only the LaTeX syntax. Do not change resume content.
4. Recompile and confirm the one-page constraint is preserved.
5. Do not modify `app/latex.py` unless the bug is in the template, not the output.
