const readline = require("readline");

function trap(height) {
  var n = height.length;
  if (n < 3) return 0;

  var left = 0;
  var right = n - 1;
  var left_max = 0;
  var right_max = 0;
  var water = 0;

  while (left < right) {
    if (height[left] < height[right]) {
      if (height[left] >= left_max) left_max = height[left];
      else water += left_max - height[left];
      ++left;
    } else {
      if (height[right] >= right_max) right_max = height[right];
      else water += right_max - height[right];
      --right;
    }
  }
  return water;
}

var input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", function (chunk) {
  input += chunk;
});
process.stdin.on("end", function () {
  var tokens = input.trim().split(/\s+/);
  var idx = 0;
  var n = parseInt(tokens[idx++], 10);
  if (isNaN(n) || n < 0) {
    process.exit(1);
  }
  var arr = [];
  for (var i = 0; i < n; i++) {
    var v = parseInt(tokens[idx++], 10);
    if (isNaN(v)) {
      process.exit(1);
    }
    arr.push(v);
  }
  var result = trap(arr);
  console.log(result);
});
