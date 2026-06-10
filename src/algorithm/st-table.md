# ST表

## 问题

给定数组 a[0..n-1]，多次询问：[L, R] 区间的最小值/最大值。

## 约束：

- 数组不修改（静态）
- 查询次数可能很多，希望查询很快

## 思路：

### 预处理
对于每个起点 i 和 长度为 2^k 的区间， [i,i+2^k-1]，预先算好这个区间的最小值，存进 st[i][k]。

> 怎么算？ 
> 从两个子区间里面来，也就是说，对于每一个 [i,k] 等于 min([i,k-1], [i+2<<(k-1),k-1])。 但是注意到 [i+2<<(k-1),k-1] 可能还没有被计算，所以要先固定k，通过 k-1 的值算出来 k。

### 查询

对于每个查询 \[l,r\]:
- 找到一个k，使得 2^k <= l-r+1
- 将原区间拆为两个子区间，\[l,l+2^k-1\], \[r-2^k+1, r], 查询这两个子区间的最小值/最大值

## 代码

```py3
def build(nums:List[int]) -> List[int]:
    n = len(nums)
    logn = n.bit_length()
    st = [[0] * logn for _ in range(n)]
    for i in range(n):
        st[i][0] = nums[i]
    for j in range(1,logn):
        pre = 1<<(j-1)
        # 对于 k = j 时，每一个可以取到的i
        for i in range(n-(1<<j)+1):
            s[i][j] = min(st[i][j-1], st[i+pre][j-1])

def query(st:List[int], l:int, r:int)->int:
    j = (r-l+1).bit_length()-1
    return min(st[l][j], st[r-(2<<j)+1][j])
```