"use strict";

var ts = require("typescript");

var CATEGORY_MAP = {
  0: "warning",
  1: "error",
  2: "suggestion",
  3: "message",
};

function main() {
  var args = process.argv.slice(2);
  var sourcePath = null;
  var typeRoots;

  for (var i = 0; i < args.length; i++) {
    if (args[i] === "--typeRoots" && i + 1 < args.length) {
      typeRoots = args[i + 1].split(",");
      i++;
    } else if (!sourcePath) {
      sourcePath = args[i];
    }
  }

  if (!sourcePath) {
    process.stderr.write("Usage: node tsc_check.js <file.ts> [--typeRoots dir1,dir2]\n");
    process.exit(2);
  }

  var options = {
    noEmit: true,
    strict: false,
    target: ts.ScriptTarget.ES2020,
    lib: ["lib.es2020.d.ts", "lib.dom.d.ts"],
    skipLibCheck: true,
  };
  if (typeRoots) {
    options.typeRoots = typeRoots;
  }

  var program = ts.createProgram([sourcePath], options);
  var diagnostics = ts.getPreEmitDiagnostics(program);

  var hasError = false;
  var output = [];

  for (var j = 0; j < diagnostics.length; j++) {
    var d = diagnostics[j];
    if (d.category === 1) {
      hasError = true;
    }
    output.push(formatDiagnostic(d));
  }

  process.stdout.write(JSON.stringify(output) + "\n");
  process.exit(hasError ? 1 : 0);
}

function formatDiagnostic(d) {
  var result = {
    code: "TS" + d.code,
    severity: CATEGORY_MAP[d.category] || "error",
    message: ts.flattenDiagnosticMessageText(d.messageText, "\n"),
  };

  if (d.file && d.start !== undefined) {
    var pos = d.file.getLineAndCharacterOfPosition(d.start);
    result.line = pos.line + 1;
    result.col = pos.character + 1;
  }

  if (d.relatedInformation && d.relatedInformation.length > 0) {
    result.relatedInformation = [];
    for (var i = 0; i < d.relatedInformation.length; i++) {
      var ri = d.relatedInformation[i];
      var riEntry = {
        message: ts.flattenDiagnosticMessageText(ri.messageText, "\n"),
      };
      if (ri.file && ri.start !== undefined) {
        var riPos = ri.file.getLineAndCharacterOfPosition(ri.start);
        riEntry.line = riPos.line + 1;
        riEntry.col = riPos.character + 1;
      }
      result.relatedInformation.push(riEntry);
    }
  }

  return result;
}

main();
