# 树状数组

每日一题：

<https://leetcode.cn/problems/count-subarrays-with-majority-element-ii/description/?envType=daily-question&envId=2026-06-26>

不知道这个算法的名字是什么，但是评论区说是树状数组

## 思路

1. 将不是 target 的数视为 -1， 否则视为 1， 然后进行前缀求和，极为pre\[n\]
2. 对于每一个 j, 就是求出所有的 i\<\j 并且 pre[j] > pre[i]。
> 一种思路是通过 排序，将j之前所有的和都插入有序数组中，然后找到 pre\[j\] 在这个数组中的left_idx，就是总共的数量。 这里不做展开，重点讲下面的算法
3. 假设 f\[n\] 记录了2的信息，现在就是在 f\[j-1\] 知道的情况下,能不能求出来f\[j\]。
4. 假设 nums\[j\] == target， 那么显然 f\[j\] = f\[j-1\] + cnt\[pre\[j-1\]\], cnt可以是一个哈希表，记录一下某个前缀和出现过多少次。
5. 详细解释一下为什么: nums\[j\] == target，说明 pre[j] = pre[j-1] + 1, 然后 f[j-1]表示在j-1时，一共有多少个i满足条件2。在j-1 -> j过程中，f[j]相对于f[j-1]新增的数量，就是pre[j-1] 的所有数量和
6. 对于 nums\[j\] != target 的场景是类似的，f[j] = f[j-1] - cnt[pre[j-1]-1]. 也就是 pre[j] 等于所有的 pre[j-1]-1，所以需要减去这部分
7. 最终答案就是 f 数组的元素和

## 算法实现


```py3

def algorithm(nums: List[int], target: int):
    c = defaultdict(int)
    c[0] = 1 ## 前缀和为0的，一定是有一个的
    s = f = ans = 0
    for x in nums:
        if x == target:
            f += cnt[s]
            s += 1
        else:
            s -= 1
            f -= cnt[s]
        cnt[s] += 1
        ans+=f
    return ans

```