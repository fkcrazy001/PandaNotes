# DSU & kruskal
## DSU 并查集
适用场景： 
- 查询两个集合是否有交集，如果有交集，那么将两个集合合并为1个。
- 查询一个元素是否在集合中，以及parent是谁。

算法：
```py3
class DSU:
    # len(parent) == 大集合中
    def __init__(self, parent):
        # parent[i] = i
        self.parent=parent
    def find(self,x):
        if self.parent[x] == x:
            return x
        self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    def jion(self,x,y):
        px,py = self.find(x),self.find(y)
        # 这里顺序不重要，只要共同指向一个祖先就行了。
        self.parent[px] = py
```

## kruskal 最小/大生成树

问题描述：

从一个由 n-1 个点形成的 无向图 `[(Ui,Vi,Wi)]` 中选出 n-1 条边，形成的一棵树，使得形成这棵树的代价最小/最大。
这棵树的代价是 所有边 之和。


算法实现：

将无向图按照 Wi 进行排序，构造一个已经加入这棵树的边集合。依此从排好序的图中选出 (u,v,w), 
如果 u,v 构成的边在集合中没有环路，那么将这条边加入这个树中，总构造成本加上w。
集合中的元素达到n-1时，树构造完成。

```py3
# 集合使用 DSU 实现

def minBuildTree(graph:List[List[]], n:int) -> int:
    dsu = DSU(list(range(n)))
    graph.sort(key=lambda x: x[2])
    cost = 0
    np = 0
    for u,v,w in graph:
        if dsu.find(u) == dsu.find(v):
            # node u and v already in dsu, skip
            continue
        cost+=w
        dsu.jion(u,v)
        np+=1
        if np == n-1:
            break
    return cost if np == n-1 else -1

```