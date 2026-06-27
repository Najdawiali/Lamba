const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const appDir = path.join(__dirname, 'app');
const componentsDir = path.join(__dirname, 'components');

const walkSync = (dir, filelist = []) => {
  if (fs.existsSync(dir)) {
    fs.readdirSync(dir).forEach(file => {
      const dirFile = path.join(dir, file);
      try {
        filelist = fs.statSync(dirFile).isDirectory()
          ? walkSync(dirFile, filelist)
          : filelist.concat(dirFile);
      } catch (err) { }
    });
  }
  return filelist;
};

const files = [...walkSync(appDir), ...walkSync(componentsDir)].filter(f => f.endsWith('.tsx'));

let errorsFound = 0;

files.forEach(file => {
  const code = fs.readFileSync(file, 'utf8');
  try {
    const ast = parser.parse(code, {
      sourceType: 'module',
      plugins: ['jsx', 'typescript']
    });

    traverse(ast, {
      JSXExpressionContainer(path) {
        if (path.node.expression.type === 'JSXEmptyExpression') return;
        if (path.parentPath.node.type === 'JSXAttribute') return; // Ignore props

        let parent = path.parentPath;
        let inText = false;
        while (parent && parent.node.type === 'JSXElement') {
          const nameNode = parent.node.openingElement.name;
          if (nameNode.type === 'JSXIdentifier' && nameNode.name === 'Text') {
            inText = true;
            break;
          }
          parent = parent.parentPath;
        }

        if (!inText) {
          const exp = path.node.expression;
          if (exp.type === 'CallExpression') {
             console.log(`[CALL EXPR OUTSIDE TEXT] ${file}:${path.node.loc.start.line}`);
             errorsFound++;
          }
          if (exp.type === 'MemberExpression') {
             console.log(`[MEMBER EXPR OUTSIDE TEXT] ${file}:${path.node.loc.start.line}`);
             errorsFound++;
          }
        }
      }
    });
  } catch (e) {
  }
});

console.log(`Found ${errorsFound} potential errors.`);
