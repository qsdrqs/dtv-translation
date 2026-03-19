import tseslint from "typescript-eslint";

export default tseslint.config({
  files: ["**/*.ts"],
  extends: [tseslint.configs.base],
  rules: {
    "@typescript-eslint/explicit-function-return-type": "error",
    "@typescript-eslint/typedef": [
      "error",
      {
        variableDeclaration: true,
        parameter: true,
        arrowParameter: true,
        memberVariableDeclaration: true,
        propertyDeclaration: true,
      },
    ],
    "@typescript-eslint/no-explicit-any": "error",
  },
});
