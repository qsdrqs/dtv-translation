const matchValueName = /[$]?[\w-]+/g;

const replaceValueSymbols = (value, replacements) => {
  let matches;

  while ((matches = matchValueName.exec(value))) {
    const replacement = replacements[matches[0]];

    if (replacement) {
      value =
        value.slice(0, matches.index) +
        replacement +
        value.slice(matchValueName.lastIndex);

      matchValueName.lastIndex -= matches[0].length - replacement.length;
    }
  }

  return value;
};

const replaceSymbols = (css, replacements) => {
  css.walk((node) => {
    if (node.type === "decl" && node.value) {
      node.value = replaceValueSymbols(node.value.toString(), replacements);
    } else if (node.type === "rule" && node.selector) {
      node.selector = replaceValueSymbols(
        node.selector.toString(),
        replacements
      );
    } else if (node.type === "atrule" && node.params) {
      node.params = replaceValueSymbols(node.params.toString(), replacements);
    }
  });
};

const importPattern = /^:import\(("[^"]*"|'[^']*'|[^"']+)\)$/;
const balancedQuotes = /^("[^"]*"|'[^']*'|[^"']+)$/;

const getDeclsObject = (rule) => {
  const object = {};

  rule.walkDecls((decl) => {
    const before = decl.raws.before ? decl.raws.before.trim() : "";

    object[before + decl.prop] = decl.value;
  });

  return object;
};
/**
 *
 * @param {string} css
 * @param {boolean} removeRules
 * @param {'auto' | 'rule' | 'at-rule'} mode
 */
const extractICSS = (css, removeRules = true, mode = "auto") => {
  const icssImports = {};
  const icssExports = {};

  function addImports(node, path) {
    const unquoted = path.replace(/'|"/g, "");
    icssImports[unquoted] = Object.assign(
      icssImports[unquoted] || {},
      getDeclsObject(node)
    );

    if (removeRules) {
      node.remove();
    }
  }

  function addExports(node) {
    Object.assign(icssExports, getDeclsObject(node));
    if (removeRules) {
      node.remove();
    }
  }

  css.each((node) => {
    if (node.type === "rule" && mode !== "at-rule") {
      if (node.selector.slice(0, 7) === ":import") {
        const matches = importPattern.exec(node.selector);

        if (matches) {
          addImports(node, matches[1]);
        }
      }

      if (node.selector === ":export") {
        addExports(node);
      }
    }

    if (node.type === "atrule" && mode !== "rule") {
      if (node.name === "icss-import") {
        const matches = balancedQuotes.exec(node.params);

        if (matches) {
          addImports(node, matches[1]);
        }
      }
      if (node.name === "icss-export") {
        addExports(node);
      }
    }
  });

  return { icssImports, icssExports };
};

const createImports = (imports, postcss, mode = "rule") => {
  return Object.keys(imports).map((path) => {
    const aliases = imports[path];
    const declarations = Object.keys(aliases).map((key) =>
      postcss.decl({
        prop: key,
        value: aliases[key],
        raws: { before: "\n  " },
      })
    );

    const hasDeclarations = declarations.length > 0;

    const rule =
      mode === "rule"
        ? postcss.rule({
            selector: `:import('${path}')`,
            raws: { after: hasDeclarations ? "\n" : "" },
          })
        : postcss.atRule({
            name: "icss-import",
            params: `'${path}'`,
            raws: { after: hasDeclarations ? "\n" : "" },
          });

    if (hasDeclarations) {
      rule.append(declarations);
    }

    return rule;
  });
};

const createExports = (exports$1, postcss, mode = "rule") => {
  const declarations = Object.keys(exports$1).map((key) =>
    postcss.decl({
      prop: key,
      value: exports$1[key],
      raws: { before: "\n  " },
    })
  );

  if (declarations.length === 0) {
    return [];
  }
  const rule =
    mode === "rule"
      ? postcss.rule({
          selector: `:export`,
          raws: { after: "\n" },
        })
      : postcss.atRule({
          name: "icss-export",
          raws: { after: "\n" },
        });

  rule.append(declarations);

  return [rule];
};

const createICSSRules = (imports, exports$1, postcss, mode) => [
  ...createImports(imports, postcss, mode),
  ...createExports(exports$1, postcss, mode),
];

var index = {
  replaceValueSymbols,
  replaceSymbols,
  extractICSS,
  createICSSRules,
};

export { index as default };
